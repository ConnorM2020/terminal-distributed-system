import sys
import re
import json
import socket
import threading
from datetime import datetime
import uuid
import tkinter as tk
import random

# Utility for formatted logging
def log_message(message_type, details):
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] {message_type}: {details}")


class Transaction:
    def __init__(self, txn_id=None, amount=None, sender=None, receiver=None, **kwargs):
        self.id = txn_id or str(uuid.uuid4())
        self.amount = amount
        self.sender = sender
        self.receiver = receiver
        self.timestamp = datetime.now().isoformat()

    def to_dict(self):
        return {
            "id": self.id,
            "amount": self.amount,
            "sender": self.sender,
            "receiver": self.receiver,
            "timestamp": self.timestamp,
        }


class Node:
    def __init__(self, nickname, address, log_callback=None):
        self.node_id = str(uuid.uuid4())
        self.nickname = nickname
        self.address = address
        self.balance = 1000.0
        self.peers = []
        self.transactions = {}
        self.running = True
        self.transaction_counter = 0
        self.lamport_clock = 0
        self.log_callback = log_callback
        self.failure_simulation = False  # Simulate failures (True to enable)
        self.drop_probability = 0.3     # 30% chance of dropping messages
        self.processed_transaction_ids = set()
        self.balances = {self.address: 1000.0}

        # Validate IP Address
        host, port = self.address.split(":")
        try:
            socket.inet_aton(host)
        except socket.error:
            raise ValueError(f"Invalid IP address: {host}")

        # Create a UDP Socket
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.bind((host, int(port)))
        self.log("Node Start", f"{self.nickname} listening on {self.address} (UDP)")

    def disconnect(self):
        self.log("Node Disconnection", "Simulating node disconnection.")
        self.running = False
        self.udp_socket.close()

    def reconnect(self):
        self.log("Node Reconnection", "Reconnecting the node.")
        self.running = True
        host, port = self.address.split(":")
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.bind((host, int(port)))
        threading.Thread(target=self.listen, daemon=True).start()

    def increment_clock(self):
        self.lamport_clock += 1
        return self.lamport_clock
    
    def update_clock(self, incoming_timestamp):
        self.lamport_clock = max(self.lamport_clock, incoming_timestamp) + 1

    def log(self, log_type, message):
        if self.log_callback:
            self.log_callback(f"[{log_type}] {message}")
        else:
            log_message(log_type, message)

    def process_transaction(self, txn):
        if txn.id in self.transactions:
            return False, "Transaction already processed."

        # Add transaction to the processed set and local transaction log
        self.processed_transaction_ids.add(txn.id)
        self.transactions[txn.id] = txn

        # Update receiver's balance
        if txn.receiver in self.balances:
            self.balances[txn.receiver] += txn.amount
        else:
            self.balances[txn.receiver] = txn.amount  # Create the account if it doesn't exist

        # Update sender's balance
        if txn.sender in self.balances:
            self.balances[txn.sender] -= txn.amount
            if self.balances[txn.sender] < 0:
                return False, "Insufficient funds."
        else:
            return False, f"Sender account '{txn.sender}' does not exist."

        self.log("Transaction Processed", f"{txn.sender} -> {txn.receiver}: {txn.amount}")
        self.log("Balances Updated", f"Current Balances: {self.balances}")

        # Synchronize with peers after processing the transaction
        self.synchronize_transactions()

        return True, "Transaction processed successfully."

    
    def send_transaction(self, receiver_address, amount):
        # Prevent sending a transaction to self
        if receiver_address == self.address:
            self.log("Error", "Cannot send transaction to self.")
            return

        # Ensure the receiver is a valid peer
        if receiver_address not in self.peers:
            self.log("Error", f"Cannot send transaction: {receiver_address} is not a peer.")
            return

        # Ensure sufficient funds in the sender's account
        if self.address not in self.balances or self.balances[self.address] < amount:
            self.log("Error", "Insufficient balance in the specified account.")
            return

        # Create a unique transaction ID
        txn_id = f"txn-{self.address}-{self.transaction_counter}"
        self.transaction_counter += 1

        # Increment the Lamport clock
        timestamp = self.increment_clock()

        # Create the transaction object
        txn = Transaction(
            txn_id=txn_id,
            amount=amount,
            sender=self.address,
            receiver=receiver_address,
            timestamp=timestamp,
        )

        # Deduct the amount from the sender's balance
        self.balances[self.address] -= amount
        self.transactions[txn.id] = txn

        # Log balance deduction on the sending node
        self.log("Balance Deducted", f"{self.address}: New Balance: {self.balances[self.address]}")

        # Broadcast the transaction
        if self.broadcast_transaction(txn):
            self.log("Transaction Sent", f"{self.address} -> {receiver_address}: {amount}")
            # Synchronize balances and transactions across the network
            self.synchronize_transactions()
        else:
            self.log("Error", f"Failed to send transaction to {receiver_address}")

    def broadcast_transaction(self, txn):
        if not self.peers:
            self.log("Warning", "No peers available to broadcast the transaction.")
            return False  # No peers to broadcast to

        success = False
        for peer in self.peers:
            try:
                self.send_udp_message("transaction", txn.to_dict(), peer)
                self.log("Broadcast", f"Transaction broadcasted to peer: {peer}")
                success = True
            except Exception as e:
                self.log("Error", f"Failed to broadcast transaction to {peer}: {e}")

        return success

    def send_ping(self, peer_address):
        # Validate the peer address format
        if not re.match(r"^\d{1,3}(\.\d{1,3}){3}:\d+$", peer_address):
            self.log("Error", f"Invalid peer address: {peer_address}. Format: IP:PORT")
            return

        # Add the peer to the sender's peer list
        self.add_peer(peer_address)

        # Send the ping message
        self.send_udp_message("ping", {"data": "Ping"}, peer_address)
        self.log("Ping Sent", f"Ping sent to {peer_address}")


    def send_udp_message(self, message_type, data, peer_address):
        # Simulate message drop
        if self.failure_simulation and random.random() < self.drop_probability:
            self.log("Failure Simulation", f"Message to {peer_address} dropped.")
            return  # Simulate message drop

        if not re.match(r"^\d{1,3}(\.\d{1,3}){3}:\d+$", peer_address):
            self.log("Error", f"Invalid peer address: {peer_address}. Format: IP:PORT")
            return

        message = {
            "message_id": str(uuid.uuid4()),
            "type": message_type,
            "data": data,
        }
        try:
            peer_host, peer_port = peer_address.split(":")
            self.udp_socket.sendto(json.dumps(message).encode("utf-8"), (peer_host, int(peer_port)))
            self.log("Message Sent", f"To {peer_address}: {message}")
        except Exception as e:
            self.log("Error", f"Failed to send message to {peer_address}: {e}")

    def handle_udp_message(self, data, addr):
        try:
            # Decode and parse the incoming JSON message
            message = json.loads(data.decode("utf-8"))
            sender_address = f"{addr[0]}:{addr[1]}"
            message_type = message.get("type")

            # Ensure the message type exists
            if not message_type:
                self.log("Error", f"Message type missing from {sender_address}: {message}")
                return

            # Log the received message
            self.log("Message Received", f"From {sender_address}: {message_type}")

            # Handle specific message types
            if message_type == "transaction":
                txn_data = message.get("data", {})
                # Validate transaction fields before creating the object
                required_fields = ["id", "amount", "sender", "receiver", "timestamp"]
                if not all(field in txn_data for field in required_fields):
                    self.log("Error", f"Incomplete transaction data from {sender_address}: {txn_data}")
                    return
                txn = Transaction(**txn_data)
                success, msg = self.process_transaction(txn)
                self.log("Transaction Processed" if success else "Transaction Failed", msg)

            elif message_type == "ping":
                # Handle ping and add sender to peers
                self.add_peer(sender_address)
                self.log("Ping Received", f"Ping received from {sender_address}")

                # Respond to the ping with an acknowledgment
                self.send_udp_message("ping_ack", {"data": "Pong"}, sender_address)

            elif message_type == "ping_ack":
                # Log ping acknowledgment
                self.log("Ping", f"Acknowledged from {sender_address}")
                self.add_peer(sender_address)

            elif message_type == "details_request":
                # Send node details in response
                self.send_node_details(sender_address)

            elif message_type == "discovery_request":
                # Handle discovery request and share peer list
                self.handle_discovery_request(sender_address)

            elif message_type == "balance_request":
                # Respond to balance request
                self.handle_balance_request(sender_address)

            elif message_type == "balance_response":
                # Process balance response
                balance_data = message.get("data", {})
                self.handle_balance_response(balance_data, sender_address)

            elif message_type == "sync_request":
                 # Prepare data to send back
                sync_data = {
                    "balances": self.balances,
                    "transactions": self.get_all_transactions(),
                    "peers": self.peers,
                }
                self.send_udp_message("sync_response", sync_data, sender_address)
                
            elif message_type == "sync_response":
                self.log("Sync Response", f"Received sync response from {sender_address}")

                # Extract data from the response
                data = message.get("data", {})
                incoming_balances = data.get("balances", {})
                incoming_transactions = data.get("transactions", [])
                incoming_peers = data.get("peers", [])

                # Merge incoming data
                self.merge_balances(incoming_balances)
                self.merge_transactions(incoming_transactions)
                self.merge_peers(incoming_peers)

                self.log("Sync Complete", "Synchronization completed successfully.")
                self.log("Balances", f"Updated Balances: {self.balances}")
                self.log("Peers", f"Updated Peers: {self.peers}")
                        
            else:
                # Log unknown message types
                self.log("Error", f"Unknown message type received from {sender_address}: {message_type}")

        except json.JSONDecodeError as e:
            # Handle invalid JSON message
            self.log("Error", f"Invalid JSON data received from {addr}: {e}")

        except Exception as e:
            # Handle unexpected errors
            self.log("Error", f"Handling message from {addr}: {e}")

    
    def get_all_transactions(self):
        return [txn.to_dict() for txn in self.transactions.values()]

    def merge_transactions(self, peer_transactions):
        for txn_data in peer_transactions:
            txn = Transaction(**txn_data)
            if txn.id not in self.processed_transaction_ids:
                self.processed_transaction_ids.add(txn.id)  # Add ID to processed set
                self.transactions[txn.id] = txn
                self.log("Transaction Merged", f"Added transaction {txn.id} from peer.")
            else:
                self.log("Transaction Skipped", f"Duplicate transaction {txn.id} ignored.")
    
    def merge_peers(self, incoming_peers):
        for peer in incoming_peers:
            if peer != self.address and peer not in self.peers:
                self.peers.append(peer)
                self.log("Peer Added", f"Added peer {peer}")

    def merge_balances(self, incoming_balances):
        for account, balance in incoming_balances.items():
            if account in self.balances:
                # Update balance to the latest value from peers
                self.balances[account] = max(self.balances[account], balance)
            else:
                self.balances[account] = balance
        self.log("Balances Merged", f"Updated Balances: {self.balances}")


    def add_peer(self, peer_address):
        if not re.match(r"^\d{1,3}(\.\d{1,3}){3}:\d+$", peer_address):
            self.log("Error", f"Invalid peer address: {peer_address}")
            return
        if peer_address in self.peers or peer_address == self.address:
            self.log("Peer", f"{peer_address} is already in the list.")
            return
        self.peers.append(peer_address)
        self.log("Peer Added", f"{peer_address}")
        # Broadcast updated peer list
        for peer in self.peers:
            self.send_udp_message("discovery_response", {"peers": self.peers}, peer)

    def send_node_details(self, peer_address):
        details = {
            "nickname": self.nickname,
            "address": self.address,
            "balance": self.balance,
            "peers": self.peers,
        }
        self.send_udp_message("details_response", details, peer_address)

    def get_node_details(self):
        details = f"Node Name: {self.nickname}\n"
        details += f"Address: {self.address}\n"
        details += "Balances:\n"
        for account, balance in self.balances.items():
            details += f"  {account} - {balance:.2f}\n"  # Address and balance

        details += "Peers:\n"
        for peer in self.peers:
            details += f"  {peer}\n"  # List of peers

        tk.messagebox.showinfo("Node Details", details)

    def handle_discovery_request(self, sender_address):
        self.add_peer(sender_address)
        response = {"peers": self.peers}
        self.send_udp_message("discovery_response", response, sender_address)

    def handle_balance_request(self, sender_address):
        self.send_udp_message("balance_response", {"balance": self.balance}, sender_address)

    def handle_balance_response(self, data, sender_address):
        balance = data.get("balance")
        if balance is not None:
            self.log("Balance Received", f"{sender_address} has balance {balance}")
        else:
            self.log("Error", f"Invalid balance data received from {sender_address}")

    def request_discovery(self):
        if not self.peers:
            self.log("Warning", "No peers to request discovery from.")
            return
        for peer in self.peers:
            self.send_udp_message("discovery_request", {}, peer)

    def synchronize_transactions(self):
        if not self.peers:
            self.log("Sync", "No peers available for synchronization.")
            return
        # Send sync request to all peers
        for peer in self.peers:
            self.send_udp_message("sync_request", {}, peer)
            self.log("Sync Request Sent", f"Sent sync request to {peer}")


    def join_network(self, peer_address):
        self.log("Join Network", f"Connecting to {peer_address}")
        self.add_peer(peer_address)
        self.request_discovery() # Request discovery to retrieve the peer list
        
        # Synchronize transactions and balances
        self.log("Join Network", f"Requesting synchronization from {peer_address}")
        self.send_udp_message("sync_request", {}, peer_address)

    def listen(self):
        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(1024)
                threading.Thread(target=self.handle_udp_message, args=(data, addr)).start()
            except Exception as e:
                self.log("Error", f"Listening loop: {e}")

    def stop(self):
        self.running = False
        self.udp_socket.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python node.py <port> [<ip>]")
        sys.exit(1)

    port = int(sys.argv[1])
    ip = sys.argv[2] if len(sys.argv) > 2 else "0.0.0.0"