import json
from pathlib import Path
from typing import List
import socket
import subprocess


def save_hosts_config(
    server_ip: str = "",
    client_ips: List[str] = "",
    nfs_path: str = "",
    local_vm_path: str = "",
    xml_folder: str = "",
    json_path: str = "config.json",
    vm_names: List[str] = [],
):
    data = {}

    if Path(json_path).exists():
        with open(json_path, "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                print(f"Warning: {json_path} is not valid JSON. Overwriting.")

    if server_ip:
        data["server_ip"] = server_ip
    if client_ips:
        data["client_ips"] = client_ips
    if nfs_path:
        data["nfs_path"] = nfs_path
    if local_vm_path:
        data["local_vm_path"] = local_vm_path
    if xml_folder:
        data["xml_folder"] = xml_folder
    if vm_names:
        data["vm_names"] = vm_names

    with open(json_path, "w") as f:
        json.dump(data, f, indent=4)
    print(f"Saved host configuration to {json_path}")


def read_hosts_config(json_path="config.json"):
    try:
        with open(json_path, "r") as f:
            data = json.load(f)
        result = {}
        expected_keys = [
            "server_ip",
            "client_ips",
            "nfs_path",
            "local_vm_path",
            "xml_folder",
            "vm_names",
        ]
        for key in expected_keys:
            if key in data:
                result[key] = data[key]
        return result
    except Exception as e:
        raise RuntimeError(f"Failed to read {json_path}: {e}")


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
    return ip


def run_command(command, check=True):
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    print(f"Running command: {command}")
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed: {command}\n{result.stderr}")
    return result


def is_host_available(host_ip: str):
    try:
        output = run_command(f"ping -w 1 {host_ip}", check=False)
        if output.returncode == 0:
            return True
        else:
            print(f"{host_ip} is not reachable")
            return False
    except Exception as e:
        print(f"Error checking host availability: {e}")
        return False
