#!/usr/bin/env python3

import socket
import struct
import sys
import argparse
import os


# TFTP Constants
OP_RRQ = 1
OP_WRQ = 2
OP_DATA = 3
OP_ACK = 4
OP_ERROR = 5

DEFAULT_PORT = 69
MODE = b"octet"

TIMEOUT = 5
MAX_RETRY = 3
BLOCK_SIZE = 512


# Utility functions
def make_rrq(filename):
    return struct.pack("!H", OP_RRQ) + filename.encode() + b"\0" + MODE + b"\0"


def make_wrq(filename):
    return struct.pack("!H", OP_WRQ) + filename.encode() + b"\0" + MODE + b"\0"


def make_ack(block):
    return struct.pack("!HH", OP_ACK, block)


def make_data(block, data):
    return struct.pack("!HH", OP_DATA, block) + data


def parse_error(packet):
    _, code = struct.unpack("!HH", packet[:4])
    msg = packet[4:-1].decode()
    return code, msg



# TFTP GET (download)
def tftp_get(sock, server, filename):
    rrq = make_rrq(filename)
    sock.sendto(rrq, server)

    with open(filename, "wb") as f:
        expected_block = 1

        while True:
            for attempt in range(MAX_RETRY):
                try:
                    sock.settimeout(TIMEOUT)
                    packet, addr = sock.recvfrom(1024)

                    op = struct.unpack("!H", packet[:2])[0]

                    if op == OP_ERROR:
                        code, msg = parse_error(packet)
                        print(f"Error {code}: {msg}")
                        return

                    if op != OP_DATA:
                        continue

                    _, block = struct.unpack("!HH", packet[:4])

                    # Wrong block? ignore and wait for correct one
                    if block != expected_block:
                        continue

                    data = packet[4:]
                    f.write(data)

                    # Send ACK
                    ack = make_ack(block)
                    sock.sendto(ack, addr)

                    # Last packet?
                    if len(data) < BLOCK_SIZE:
                        print(f"Download complete: {filename}")
                        return

                    expected_block += 1
                    break

                except socket.timeout:
                    print("Timeout, retrying...")
                    sock.sendto(rrq, server) if expected_block == 1 else None

            else:
                print("Failed: no response from server.")
                return



# TFTP PUT (upload)
def tftp_put(sock, server, filename):
    if not os.path.exists(filename):
        print("Local file not found.")
        return

    wrq = make_wrq(filename)
    sock.sendto(wrq, server)

    # Wait for ACK(0)
    for attempt in range(MAX_RETRY):
        try:
            sock.settimeout(TIMEOUT)
            packet, addr = sock.recvfrom(1024)

            op, block = struct.unpack("!HH", packet[:4])

            if op == OP_ERROR:
                code, msg = parse_error(packet)
                print(f"Error {code}: {msg}")
                return

            if op == OP_ACK and block == 0:
                break
        except socket.timeout:
            print("Timeout waiting for WRQ ACK, retrying...")
            sock.sendto(wrq, server)
    else:
        print("Failed: no response from server.")
        return

    # Start sending file blocks
    with open(filename, "rb") as f:
        block_num = 1

        while True:
            data = f.read(BLOCK_SIZE)
            data_packet = make_data(block_num, data)

            for attempt in range(MAX_RETRY):
                try:
                    sock.sendto(data_packet, addr)
                    sock.settimeout(TIMEOUT)
                    packet, addr2 = sock.recvfrom(1024)

                    op, recv_block = struct.unpack("!HH", packet[:4])

                    if op == OP_ERROR:
                        code, msg = parse_error(packet)
                        print(f"Error {code}: {msg}")
                        return

                    if op == OP_ACK and recv_block == block_num:
                        break
                except socket.timeout:
                    print("Timeout sending block, retrying...")
            else:
                print("Failed: no response from server.")
                return

            if len(data) < BLOCK_SIZE:
                print("Upload complete.")
                return

            block_num += 1



# MAIN
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("host")
    parser.add_argument("action", choices=["get", "put"])
    parser.add_argument("filename")
    parser.add_argument("-p", "--port", type=int, default=DEFAULT_PORT)

    args = parser.parse_args()

    server = (args.host, args.port)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    if args.action == "get":
        tftp_get(sock, server, args.filename)
    else:
        tftp_put(sock, server, args.filename)


if __name__ == "__main__":
    main()
