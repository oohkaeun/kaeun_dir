#!/usr/bin/env python

"""
실행 명령어
python mytftp.py 203.250.133.88 get tftp.conf
python mytftp.py 203.250.133.88 put 2389001.txt
python mytftp.py genie.pcu.ac.kr -p 9988 put test.txt
"""

import socket
import struct
import sys
import argparse
import os


# TFTP Constants
# opcodes
OP_RRQ = 1
OP_WRQ = 2
OP_DATA = 3
OP_ACK = 4
OP_ERROR = 5

DEFAULT_PORT = 69
MODE = b"octet"

# 동작 관련 상수
TIMEOUT = 5 # 소켓 타임아웃
MAX_RETRY = 3 # 최대 재시도 횟수
BLOCK_SIZE = 512


# Utility functions
# Read Request 패킷 생성
def make_rrq(filename):
    return struct.pack("!H", OP_RRQ) + filename.encode() + b"\0" + MODE + b"\0"

# Write Request 패킷 생성
def make_wrq(filename):
    return struct.pack("!H", OP_WRQ) + filename.encode() + b"\0" + MODE + b"\0"

# ACK 패킷 생성
def make_ack(block):
    return struct.pack("!HH", OP_ACK, block)

# DATA 패킷 생성
def make_data(block, data):
    return struct.pack("!HH", OP_DATA, block) + data

# ERROR 패킷 생성
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

                    # 서버 ERROR 응답 시
                    if op == OP_ERROR:
                        code, msg = parse_error(packet)
                        print(f"Error {code}: {msg}")
                        return

                    # DATA 아닌 패킷 무시
                    if op != OP_DATA:
                        continue

                    # DATA에서 block 번호 가져오기
                    _, block = struct.unpack("!HH", packet[:4])

                    # 원하지 않은 블록 무시
                    if block != expected_block:
                        continue

                    data = packet[4:]
                    f.write(data) # 수신 데이터 기록

                    # Send ACK
                    ack = make_ack(block)
                    sock.sendto(ack, addr)

                    # Last packet 판단
                    if len(data) < BLOCK_SIZE:
                        print(f"Download complete: {filename}")
                        return

                    # 다음 블록 기다림
                    expected_block += 1
                    break

                except socket.timeout: # 타임아웃 발생 시
                    print("Timeout, retrying...")
                    #sock.sendto(rrq, server) if expected_block == 1 else None
                    # 아직 첫 블록(=RRQ 응답)을 못받은 상태라면 RRQ를 재전송
                    if expected_block == 1:
                        sock.sendto(rrq, server)

            else: # 재시도 횟수 초과로 중단
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
            packet, addr = sock.recvfrom(1024) # 최초 응답을 보낸 포트 획득

            op, block = struct.unpack("!HH", packet[:4])

            if op == OP_ERROR:
                code, msg = parse_error(packet)
                print(f"Error {code}: {msg}")
                return

            # ACK(0)를 받으면 업로드 시작
            if op == OP_ACK and block == 0:
                break
        except socket.timeout: # ACK(0) 못받음 -> WRQ 재전송
            print("Timeout waiting for WRQ ACK, retrying...")
            sock.sendto(wrq, server)
    else: # MAX_RETRY 동안 응답 없으면 실패 처리
        print("Failed: no response from server.")
        return

    # Start sending file blocks: 파일 블록 전송 루프
    with open(filename, "rb") as f:
        block_num = 1

        while True:
            data = f.read(BLOCK_SIZE)
            data_packet = make_data(block_num, data)

            # 각 블록 전송 후 ACK(block_num) 도착 대기
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

                    # 서버가 ACK을 보내면 다음 블록으로 진행
                    if op == OP_ACK and recv_block == block_num:
                        break
                except socket.timeout: # Timeout 시 재전송
                    print("Timeout sending block, retrying...")

            else: # 횟수 초과로 끝
                print("Failed: no response from server.")
                return

            # 마지막 블록이면 종료
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
