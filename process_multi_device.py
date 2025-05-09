import socket
import argparse
import json
import random
import time
import struct
import threading

MULTICAST_GROUP_FIREWORKS = "224.0.0.1"
MULTICAST_GROUP_ROUND_TIMES = "224.1.1.1"
MULTICAST_PORT_FIREWORKS = 5007
MULTICAST_PORT_ROUND_TIMES = 5008
BUFFER_SIZE = 1024


def send_token(next_ip, next_port, token):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    round_start = time.time()
    round_duration = round_start - token["timestamp"]
    token["timestamp"] = round_start

    message = json.dumps({"type": "round_time", "duration": round_duration})
    sock.sendto(
        message.encode(), (MULTICAST_GROUP_ROUND_TIMES, MULTICAST_PORT_ROUND_TIMES)
    )
    sock.sendto(json.dumps(token).encode(), (next_ip, next_port))


def multicast_firework(process_id, round_number):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
    message = f"Firework from {process_id} in round {round_number}"
    sock.sendto(message.encode(), (MULTICAST_GROUP_FIREWORKS, MULTICAST_PORT_FIREWORKS))


def listen_multicast():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", MULTICAST_PORT_FIREWORKS))
    mreq = struct.pack(
        "4sl", socket.inet_aton(MULTICAST_GROUP_FIREWORKS), socket.INADDR_ANY
    )
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    def receive():
        while True:
            data, _ = sock.recvfrom(BUFFER_SIZE)
            print("[Multicast] Received:", data.decode())

    threading.Thread(target=receive, daemon=True).start()


def main(args):
    print(
        f"[Process {args.id}] Starting with initial probability {args.initial_p} and k = {args.k}"
    )
    try:
        listen_multicast()
        probability = args.initial_p
        rounds_without_firework = 0
        total_rounds = 0

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((args.ip, args.port))

        print(
            f"[Process {args.id}] Started on port {args.port}, next = {args.next_port}"
        )

        while True:
            data, _ = sock.recvfrom(BUFFER_SIZE)
            token = json.loads(data.decode())
            if token.get("silent_rounds") and token["silent_rounds"] >= args.k:
                print(
                    f"[Process {args.id}] Received token with silent rounds >= k, terminating."
                )
                send_token(args.next_ip, args.next_port, token)
                break
            total_rounds += 1
            print(f"[Process {args.id}] Received token in round {token['round']}")

            if random.random() < probability:
                print(f"[Process {args.id}] FIREWORK!")
                multicast_firework(args.id, token["round"])
                rounds_without_firework = 0
            else:
                rounds_without_firework += 1

            probability /= 2
            token["round"] += 1

            if rounds_without_firework >= args.k:
                print(f"[Process {args.id}] Terminating after {token['round']} rounds")
                token["silent_rounds"] = rounds_without_firework
                send_token(args.next_ip, args.next_port, token)
                break

            time.sleep(0.1)
            send_token(args.next_ip, args.next_port, token)

    finally:
        sock.close()
        print(f"[Process {args.id}] Socket closed.")


if __name__ == "__main__":
    print("Starting process...")
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, required=True)
    parser.add_argument("--ip", type=str, required=True)  # own IP
    parser.add_argument("--next_ip", type=str, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--next_port", type=int, required=True)
    parser.add_argument("--initial_p", type=float, default=0.5)
    parser.add_argument("--k", type=int, default=5)
    main(parser.parse_args())
