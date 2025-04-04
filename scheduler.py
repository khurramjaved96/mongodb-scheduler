import subprocess
import sys
import time
import json
from pymongo import MongoClient
import os
import signal

def getCommand():
    """
    Retrieves the next command to execute from the MongoDB queue.
    Updates the command's status to 1 (in progress) when retrieved.
    
    Returns:
        tuple: (command string, directory string, document ID) or ("none", "none", "none") if no command available
    """
    with open('connection_string.txt', 'r') as f:
        connection_string = f.read()
    client = MongoClient(connection_string)
    try:
        # Find commands with status 0 (pending) and update to status 1 (in progress)
        filter = {'status': 0}
        project = {
            'command': 1,
            'priority': 1,
            'directory': 1
        }
        sort = [('priority', -1), ('rand', 1)]  # Sort by priority (descending) and random value
        
        collation = {}

        result = client['experiments']['queue'].find_one_and_update(
            filter=filter,
            update={'$set': {'status': 1}},
            projection=project,
            collation=collation,
            sort=sort
        )
        print(result)
        if result:
            return result['command'], result.get('directory', '.'), result["_id"]
        return "none", "none", "none"

    except Exception as e:
        print("Exception", e)
        return "none", "none", "none"


def MoveAndDeleteDocument(id):
    """
    Moves a completed command from the queue to the completed collection.
    
    Args:
        id: MongoDB document ID of the completed command
    """
    with open('connection_string.txt', 'r') as f:
        connection_string = f.read()
    client = MongoClient(connection_string)
    try:
        # Move document to completed collection instead of deleting
        doc = client['experiments']['queue'].find_one({"_id": id})
        if doc:
            client['experiments']['completed'].insert_one(doc)
            client['experiments']['queue'].delete_one({"_id": id})
    except Exception as e:
        print(e)


# Initialize process tracking
list_of_process = []  # List to track all running processes
process_to_id = {}  # Dictionary to map processes to their MongoDB document IDs

# Determine number of CPU cores for parallel processing
cpu_count = os.cpu_count()

# Initialize process list with dummy processes
for i in range(cpu_count):
    list_of_process.append(subprocess.Popen('sleep 0.001', shell=True))
    time.sleep(0.001)

def cleanup():
    """
    Handles graceful shutdown by:
    1. Terminating all running processes
    2. Moving all in-progress commands to the queue
    3. Exiting the script
    """
    print("\nCleaning up...")
    # Kill all running processes
    for p in list_of_process:
        if p.poll() is None:  # Process is still running
            p.terminate()
            try:
                p.wait(timeout=1)  # Wait for process to terminate
            except subprocess.TimeoutExpired:
                p.kill()  # Force kill if it doesn't terminate
    
    # Move all in-progress commands to completed collection
    if process_to_id:
        with open('connection_string.txt', 'r') as f:
            connection_string = f.read()
        client = MongoClient(connection_string)
        for doc_id in process_to_id.values():
            # Move document to completed collection with status 0
            doc = client['experiments']['queue'].find_one({"_id": doc_id})
            if doc:
                doc['status'] = 0
                client['experiments']['completed'].insert_one(doc)
                client['experiments']['queue'].delete_one({"_id": doc_id})
    sys.exit(0)

def signal_handler(sig, frame):
    """
    Handles interrupt signals (Ctrl+C) and termination signals.
    """
    cleanup()

# Register signal handlers for graceful shutdown
signal.signal(signal.SIGINT, signal_handler)  # Handle Ctrl+C
signal.signal(signal.SIGTERM, signal_handler)  # Handle termination signal

# Main processing loop
while True:
    counter = 0
    for p in list_of_process:
        if(p.poll() != None):  # Process has completed
            # Handle completed process
            if p in process_to_id:
                doc_id = process_to_id[p]
                if p.returncode == 0:  # Success
                    MoveAndDeleteDocument(doc_id)  # Move to completed collection
                else:  # Failure
                    print("Failure", p.returncode)
                    with open('connection_string.txt', 'r') as f:
                        connection_string = f.read()
                    client = MongoClient(connection_string)
                    # Handle failed experiment
                    doc = client['experiments']['queue'].find_one({"_id": doc_id})
                    if doc:
                        # Create log entry
                        log_entry = {
                            "command": doc['command'],
                            "directory": doc.get('directory', '.'),
                            "return_code": p.returncode,
                            "timestamp": time.time(),
                            "priority": doc.get('priority', 0),
                            "original_doc_id": doc_id,
                            "status": "failed",
                            "attempt_count": doc.get('attempt_count', 0) + 1,
                            "error_message": f"Process failed with return code {p.returncode}"
                        }
                        client['experiments']['log'].insert_one(log_entry)
                        
                        # # Move to failed collection
                        # failed_doc = {
                        #     **doc,  # Include all original document fields
                        #     "return_code": p.returncode,
                        #     "timestamp": time.time(),
                        #     "attempt_count": doc.get('attempt_count', 0) + 1,
                        #     "error_message": f"Process failed with return code {p.returncode}"
                        # }
                        # client['experiments']['failed'].insert_one(failed_doc)
                        
                        # Remove from queue
                        client['experiments']['queue'].delete_one({"_id": doc_id})
                del process_to_id[p]  # Remove the mapping
            
            # Get and start new command
            command, directory, doc_id = getCommand()
            if(command != "none"):
                print(f"Running command in {directory}: {command}")
                new_process = subprocess.Popen(
                    command,
                    shell=True,
                    cwd=directory  # Set the working directory
                )
                list_of_process[counter] = new_process
                process_to_id[new_process] = doc_id  # Store the mapping
            time.sleep(0.1)
        counter+=1

    time.sleep(0.1)  # Main loop delay 