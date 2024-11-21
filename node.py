import sys
import re
import json
import socket
import threading
from datetime import datetime

# Transaction class to handle individual transactions
class Transaction:
    def __init__(self, txn_id=None, amount=None, sender=None, receiver=None, **kwargs):
        self.id = txn_id or kwargs.get("id")
        self.amount = amount
        self.sender = sender
        self.receiver = receiver
        self.timestamp = datetime.now().isoformat()

    def to_dict(self):
        """Convert the transaction object to a dictionary."""
        return {
            "id": self.id,
            "amount": self.amount,
            "sender": self.sender,
            "receiver": self.receiver,
            "timestamp": self.timestamp,
        }


# Node class to represent a node in the network
class Node:
    def __init__(self, nickname, address):
        self.nickname = nickname
        self.address = address
        self.balance = 1000.0  # Initial balance for the node
        self.peers = []  # List of connected peer addresses
        self.transactions = {}  # Dictionary of processed transactions
        self.running = True  # Flag to keep the node running
        self.transaction_counter = 0  # Counter for transaction IDs
        
        # Create a single UDP socket for both sending and receiving
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.bind((self.address.split(":")[0], int(self.address.split(":")[1])))
        print(f"Node {self.nickname} listening on {self.address} (UDP)")


    def process_transaction(self, txn):
        """Process a received transaction."""
        if txn.id in self.transactions:
            return False, "Transaction already processed."

        if txn.receiver == self.address:
            # Update receiver balance
            self.balance += txn.amount
            self.transactions[txn.id] = txn
            return True, "Transaction received and balance updated."

        return False, "Transaction not for this node."

    def send_transaction(self, receiver_address, amount):
        """Create and send a transaction to a receiver."""
        if self.balance < amount:
            print("\nInsufficient balance to send transaction.")
            return

        txn_id = f"txn-{self.transaction_counter}"
        self.transaction_counter += 1

        # Create the transaction
        txn = Transaction(
            txn_id=txn_id, amount=amount, sender=self.address, receiver=receiver_address
        )

        # Deduct balance from the sender
        self.balance -= amount
        self.transactions[txn.id] = txn

        # Log transaction details
        print(f"\nSending transaction to {receiver_address}:")
        print(json.dumps(txn.to_dict(), indent=4))

        # Broadcast the transaction to the receiver
        message = json.dumps({"type": "transaction", "data": txn.to_dict()})
        self.send_udp_message(message, receiver_address)

    def send_udp_message(self, message, peer_address):
        """Send a UDP message to a peer using the node's single socket."""
        try:
            peer_host, peer_port = peer_address.split(":")
            self.udp_socket.sendto(message.encode("utf-8"), (peer_host, int(peer_port)))
        except (socket.gaierror, ConnectionResetError):
            print(f"\nError sending message to {peer_address}. Removing from peers list.")
            if peer_address in self.peers:
                self.peers.remove(peer_address)

    def listen(self):
        """Start listening for UDP messages using the node's existing socket."""
        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(1024)
                threading.Thread(target=self.handle_udp_message, args=(data, addr)).start()
            except ConnectionResetError:
                print("\nConnection reset by remote host. Ignoring and continuing to listen.")
            except Exception as e:
                print(f"\nError in listening loop: {e}")



    def handle_udp_message(self, data, addr):
        """Handle incoming UDP messages."""
        try:
            message = json.loads(data.decode("utf-8"))

            # Always resolve the sender's address using its original port
            sender_address = f"{addr[0]}:{addr[1]}"

            if message["type"] == "transaction":
                txn_data = message["data"]
                txn = Transaction(**txn_data)
                success, msg = self.process_transaction(txn)
                if success:
                    print(f"\nTransaction processed successfully:")
                    print(f"- {txn.to_dict()}")
                else:
                    print(f"\nTransaction failed: {msg}")

            elif message["type"] == "ping":
                print(f"\nPing received from {sender_address}. Message: {message['data']}")
                self.add_peer(sender_address)

            elif message["type"] == "details_request":
                print(f"\nDetails request received from {sender_address}")
                self.send_node_details(sender_address)

            elif message["type"] == "details_response":
                print(f"\nNode details received:")
                details = message["data"]
                print(f"- Nickname: {details['nickname']}")
                print(f"- Address: {details['address']}")
                print(f"- Balance: {details['balance']}")
                print(f"- Connected Peers: {', '.join(details['peers']) if details['peers'] else 'None'}")
                self.add_peer(details["address"])
            else:
                print(f"\nUnknown message type received from {addr}: {message}")

        except Exception as e:
            print(f"\nError handling message from {addr}: {e}")

    def add_peer(self, peer_address):
        """Add a peer to the peers list if not already present and validate address."""
        # Regex to match IP:PORT format
        if not re.match(r"^\d{1,3}(\.\d{1,3}){3}:\d+$", peer_address):
            print("\nInvalid address format. Please use IP:PORT format (e.g., 127.0.0.1:5001).")
            return
        
        if peer_address not in self.peers and peer_address != self.address:
            self.peers.append(peer_address)
            print(f"\nNode {peer_address} added to peers list.")


    def send_node_details(self, requester_addr):
        """Send this node's details back to the requester."""
        details = {
            "nickname": self.nickname,
            "address": self.address,
            "balance": self.balance,
            "peers": self.peers,
        }
        message = json.dumps({"type": "details_response", "data": details})
        self.send_udp_message(message, requester_addr)
        print(f"\nNode details sent to {requester_addr}")

    def ping_all(self):
        """Ping all connected peers."""
        if not self.peers:
            print("\nNo peers to ping.")
            return

        print("\nPinging all peers...")
        for peer in self.peers[:]:  # Iterate over a copy of the list to safely modify it
            try:
                message = json.dumps({"type": "ping", "data": f"Hello from {self.nickname}"})
                self.send_udp_message(message, peer)
                print(f"Ping sent to {peer}")
            except Exception as e:
                print(f"\nError pinging {peer}: {e}")
                if peer in self.peers:
                    self.peers.remove(peer)

    def stop(self):
        """Stop the node."""
        self.running = False


# Helper functions
def print_menu():
    """Print the Node menu."""
    print("\n=== Node Menu ===")
    print("1. List Peers")
    print("2. Add Peer")
    print("3. Send Transaction")
    print("4. List Transactions")
    print("5. Send Ping")
    print("6. Get Node Details")
    print("7. Ping All")
    print("8. Exit")


def start_node(port):
    nickname = f"Node-{port}"
    address = f"127.0.0.1:{port}"
    node = Node(nickname, address)
    threading.Thread(target=node.listen, daemon=True).start()

    while True:
        print_menu()
        choice = input("Enter your choice: ")

        if choice == "1":
            if not node.peers:
                print("\nNo peers connected.")
            else:
                print("\nConnected peers:")
                for peer in node.peers:
                    print(f"- {peer}")
        elif choice == "2":
            peer = input("Enter peer address (e.g., 127.0.0.1:5001): ")
            node.add_peer(peer)
        elif choice == "3":
            receiver = input("Enter receiver address: ")
            amount = float(input("Enter amount: "))
            node.send_transaction(receiver, amount)
        elif choice == "4":
            if not node.transactions:
                print("\nNo transactions available.")
            else:
                for txn in node.transactions.values():
                    print(f"- {txn.to_dict()}")
        elif choice == "5":
            peer = input("Enter peer address to ping: ")
            node.send_udp_message(json.dumps({"type": "ping", "data": "Hello"}), peer)
        elif choice == "6":
            peer = input("Enter peer address to request details: ")
            node.send_udp_message(json.dumps({"type": "details_request"}), peer)
        elif choice == "7":
            node.ping_all()
        elif choice == "8":
            node.stop()
            sys.exit(0)
        else:
            print("Invalid choice. Try again.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python node.py <port>")
        sys.exit(1)

    start_node(int(sys.argv[1]))
