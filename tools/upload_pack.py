#!/usr/bin/env python3
"""Install a font pack on a Meshtastic device, over the protobuf API's XModem file transfer.

  upload_pack.py --port /dev/cu.usbmodem101 out/cjk12.mfp
  upload_pack.py --host 10.0.1.2 out/cjk12.mfp --reboot

The pack goes to /fonts/<name>.mfp. The device loads its packs at boot (until it can reload them by itself, use
--reboot). Needs the meshtastic Python package.
"""
import argparse, os, struct, sys, threading, time, zlib

from pubsub import pub
from meshtastic.protobuf import mesh_pb2, xmodem_pb2

CHUNK = 128  # the XModem buffer of the protobuf API
RETRIES = 5
TIMEOUT = 10.0

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


def on_xmodem(packet, interface):
    with reply_ready:
        replies.append(packet.control)
        reply_ready.notify()


def exchange(iface, control, seq=0, data=b""):
    """Sends one XModem packet and returns the device's reply (a Control value), None on timeout."""
    msg = mesh_pb2.ToRadio()
    msg.xmodemPacket.control = control
    msg.xmodemPacket.seq = seq
    msg.xmodemPacket.buffer = data
    msg.xmodemPacket.crc16 = crc16_ccitt(data)
    with reply_ready:
        replies.clear()
        iface._sendToRadio(msg)
        if not reply_ready.wait_for(lambda: replies, TIMEOUT):
            return None
        return replies.pop(0)


def check_pack(data):
    if len(data) < 64 or data[:4] != b"MFPK":
        sys.exit("not a font pack")
    version, _, size, crc = struct.unpack_from("<HHII", data, 4)
    if version != 1 or size != len(data) or zlib.crc32(data[16:]) != crc:
        sys.exit("the pack is damaged (version, size or CRC)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pack")
    ap.add_argument("--port", help="serial port")
    ap.add_argument("--host", help="TCP host (the device's IP address)")
    ap.add_argument("--name", help="file name on the device (default: the pack's file name)")
    ap.add_argument("--reboot", action="store_true", help="reboot the device afterwards, so it loads the pack")
    a = ap.parse_args()

    data = open(a.pack, "rb").read()
    check_pack(data)
    name = a.name or os.path.basename(a.pack)
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
    C = xmodem_pb2.XModem
    try:
        reply = exchange(iface, C.SOH, 0, target.encode())
        if reply != C.ACK:
            sys.exit("the device refused %s (%s)" % (target, reply))
        chunks = [data[i:i + CHUNK] for i in range(0, len(data), CHUNK)]
        start = time.time()
        for seq, chunk in enumerate(chunks, 1):
            for attempt in range(RETRIES):
                reply = exchange(iface, C.SOH, seq & 0xFFFF, chunk)
                if reply == C.ACK:
                    break
            else:
                exchange(iface, C.CAN)
                sys.exit("packet %d not acknowledged (%s): transfer cancelled" % (seq, reply))
            if seq % 50 == 0 or seq == len(chunks):
                print("\r%s: %d / %d bytes" % (target, min(seq * CHUNK, len(data)), len(data)), end="", flush=True)
        if exchange(iface, C.EOT) != C.ACK:
            sys.exit("\nend of transfer not acknowledged")
        print("\n%d bytes in %.0f s" % (len(data), time.time() - start))
        if a.reboot:
            iface.localNode.reboot(3)
            print("the device reboots")
    finally:
        iface.close()


if __name__ == "__main__":
    main()
