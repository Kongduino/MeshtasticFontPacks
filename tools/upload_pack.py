#!/usr/bin/env python3
"""Install a font pack on a Meshtastic device, over the protobuf API's XModem file transfer.

  upload_pack.py --port /dev/cu.usbmodem101 out/cjk12.mfp
  upload_pack.py --host 10.0.1.2 out/cjk12.mfp
  upload_pack.py --port /dev/cu.usbmodem101 --remove cjk12.mfp

The pack goes to /fonts/<name>.mfp: the device receives it into a partial file, checks it, then puts it in place
(replacing a pack of the same name, even in use) and uses it without a reboot. Needs the meshtastic Python package.
"""
import argparse, os, struct, sys, threading, time, zlib

from pubsub import pub
from meshtastic.protobuf import mesh_pb2, xmodem_pb2

CHUNK = 128  # the XModem buffer of the protobuf API
RETRIES = 5
TIMEOUT = 3.0  # a packet's reply (an erase can take a few hundred ms)
END_TIMEOUT = 30.0  # the end of the transfer: the device checks the whole pack first

replies = []
reply_ready = threading.Condition()


def crc16_ccitt(data):
    """The firmware's CRC-16 (xmodem.cpp, crc16_ccitt)."""
    crc = 0
    for b in data:
        crc = ((crc >> 8) | (crc << 8)) & 0xFFFF
        crc ^= b
        crc ^= (crc & 0xFF) >> 4
        crc ^= (crc << 12) & 0xFFFF
        crc ^= ((crc & 0xFF) << 5) & 0xFFFF
    return crc


def on_log(line, interface):
    """The device's font pack messages, when its API log is on (security.debug_log_api_enabled)."""
    if "FontPacks" in line or "abandon" in line:
        print("\r  device: " + line.strip())


def on_xmodem(packet, interface):
    with reply_ready:
        replies.append(packet.control)
        reply_ready.notify()


def send(iface, msg):
    """Sends a ToRadio frame. Over serial, the library sleeps 100 ms after every write (StreamInterface._writeBytes),
    which would make the transfer about 10 times slower: the frame goes to the port directly."""
    from meshtastic.serial_interface import SerialInterface
    if isinstance(iface, SerialInterface) and iface.stream:
        b = msg.SerializeToString()
        iface.stream.write(bytes([0x94, 0xC3, len(b) >> 8, len(b) & 0xFF]) + b)
        iface.stream.flush()
    else:
        iface._sendToRadio(msg)


def exchange(iface, control, seq=0, data=b"", timeout=None):
    """Sends one XModem packet and returns the device's reply (a Control value), None on timeout."""
    msg = mesh_pb2.ToRadio()
    msg.xmodemPacket.control = control
    msg.xmodemPacket.seq = seq
    msg.xmodemPacket.buffer = data
    msg.xmodemPacket.crc16 = crc16_ccitt(data)
    with reply_ready:
        replies.clear()
        send(iface, msg)
        if not reply_ready.wait_for(lambda: replies, timeout or TIMEOUT):
            return None
        return replies.pop(0)


def check_pack(data):
    if len(data) < 80 or data[:4] != b"MFPK":
        sys.exit("not a font pack")
    version, _, size, crc = struct.unpack_from("<HHII", data, 4)
    if version != 2:
        sys.exit("format version %d: the firmware reads version 2 (rebuild the pack with mkfontpack.py)" % version)
    if size != len(data) or zlib.crc32(data[16:]) != crc:
        sys.exit("the pack is damaged (size or CRC)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pack", nargs="?")
    ap.add_argument("--port", help="serial port")
    ap.add_argument("--host", help="TCP host (the device's IP address)")
    ap.add_argument("--name", help="file name on the device (default: the pack's file name)")
    ap.add_argument("--remove", metavar="NAME", help="remove the pack /fonts/NAME from the device instead")
    ap.add_argument("--force", action="store_true", help="send the pack without checking it first (tests the device's check)")
    a = ap.parse_args()

    if a.remove:
        name = a.remove
    elif a.pack:
        data = open(a.pack, "rb").read()
        if not a.force:
            check_pack(data)
        name = a.name or os.path.basename(a.pack)
    else:
        sys.exit("give a pack to install, or --remove NAME")
    if not name.endswith(".mfp") or "/" in name:
        sys.exit("the name must be a plain file name ending in .mfp")
    target = "/fonts/" + name

    if a.host:
        from meshtastic.tcp_interface import TCPInterface
        iface = TCPInterface(hostname=a.host)
    else:
        from meshtastic.serial_interface import SerialInterface
        iface = SerialInterface(devPath=a.port)
    pub.subscribe(on_xmodem, "meshtastic.xmodempacket")
    pub.subscribe(on_log, "meshtastic.log.line")
    C = xmodem_pb2.XModem
    try:
        if os.environ.get("UPLOAD_TIMEOUT"):
            global TIMEOUT
            TIMEOUT = float(os.environ["UPLOAD_TIMEOUT"])
        if a.remove:
            # The device closes its packs before deleting the file (AdminModule, FontPacks::remove)
            from meshtastic.protobuf import admin_pb2
            msg = admin_pb2.AdminMessage()
            msg.delete_file_request = target
            iface.localNode._sendAdmin(msg)
            time.sleep(1)
            print("asked the device to remove", target)
            return
        reply = exchange(iface, C.SOH, 0, target.encode())
        if reply != C.ACK:
            sys.exit("the device refused %s (%s)" % (target, reply))
        chunks = [data[i:i + CHUNK] for i in range(0, len(data), CHUNK)]
        start = time.time()
        lost_acks = 0
        lost_seqs = []
        for seq, chunk in enumerate(chunks, 1):
            timed_out = False
            for attempt in range(RETRIES):
                reply = exchange(iface, C.SOH, seq & 0xFFFF, chunk)
                if reply in (C.ACK, C.CAN):  # CAN: the device stopped the transfer, retrying is pointless
                    break
                if reply is None:
                    timed_out = True
                elif reply == C.NAK and timed_out:
                    # The device NAKs a packet it already stored (wrong sequence): it took this one, and its ACK was
                    # lost on the way back. Go on with the next packet
                    lost_acks += 1
                    lost_seqs.append(seq)
                    reply = C.ACK
                    break
            if reply != C.ACK:
                exchange(iface, C.CAN)
                hint = ""
                if reply == C.CAN:
                    hint = ("\nthe device stopped the transfer (its log says why). If the pack doesn't fit, remove one first "
                            "(--remove NAME), then upload again")
                sys.exit("\npacket %d not acknowledged (%s): transfer cancelled%s" % (seq, reply, hint))
            if seq % 50 == 0 or seq == len(chunks):
                print("\r%s: %d / %d bytes" % (target, min(seq * CHUNK, len(data)), len(data)), end="", flush=True)
        # The device checks the pack (structure, CRC) and installs it before it acknowledges the end
        reply = exchange(iface, C.EOT, timeout=END_TIMEOUT)
        if reply == C.NAK:
            sys.exit("\nthe device checked the pack and refused it: nothing changed on the device")
        if reply != C.ACK:
            sys.exit("\nend of transfer not acknowledged (%s)" % reply)
        if lost_seqs and os.environ.get("UPLOAD_DEBUG"):
            print("\nlost acknowledgements at packets:", lost_seqs)
        print("\n%d bytes in %.0f s%s" % (len(data), time.time() - start,
                                         (" (%d lost acknowledgements recovered)" % lost_acks) if lost_acks else ""))
    finally:
        iface.close()


if __name__ == "__main__":
    main()
