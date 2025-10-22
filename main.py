#!/usr/bin/env python3

import typer
from typing_extensions import Annotated
from migrator.nfs_mount import (
    create_nfs_localy,
    mount_nfs,
    create_nfs_remotely,
    unmount_nfs,
)
from migrator.vm_runner import (
    run_vm_nfs,
    run_vm_scp,
    migrate_live_local,
    migrate_live_nfs,
)
from migrator.vm_manager import create_vm_on_nfs, delete_nfs_vm

app = typer.Typer()


@app.command(help="This command mounts an NFS share to a local directory.")
def mount(
    host_ip: str = typer.Argument(help="IP address of the NFS server"),
    host_folder: Annotated[
        str, typer.Option("--host-folder", "-hf", help="Folder path on the NFS server")
    ] = "/mnt/nfs",
    local_folder: Annotated[
        str, typer.Option("--local-folder", "-lf", help="Local mount point directory")
    ] = "/mnt/nfs",
):
    mount_nfs(host_ip, host_folder, local_folder)


@app.command(help="This command unmounts an NFS share from a local directory.")
def unmount(
    local_folder: Annotated[
        str, typer.Argument(help="Local mount point directory")
    ] = "/mnt/nfs",
):
    unmount_nfs(local_folder)


@app.command(help="This command create nfs share.")
def create_nfs(
    client_ips: Annotated[list[str], typer.Argument(help="Client IPs")],
    host_ip: Annotated[
        str,
        typer.Option(
            "--host-ip",
            "-H",
            help="IP address of the NFS server, to setup locally pass 127.0.0.1",
        ),
    ] = "127.0.0.1",
    folder: Annotated[
        str, typer.Option("--folder", "-f", help="Folder path on the NFS server")
    ] = "/mnt/nfs",
):
    print(f"Creating NFS share on {host_ip} for clients: {client_ips}")
    print(f"Folder: {folder}")
    if host_ip == "127.0.0.1":
        create_nfs_localy(folder, [client_ips])
    else:
        create_nfs_remotely(host_ip, folder, client_ips)


@app.command(help="Migrate a VM from a file located in NFS.")
def migrate_nfs(
    img_name: Annotated[str, typer.Argument(help="Name of the file to run")],
):
    run_vm_nfs(img_name)


@app.command(help="Migrate a VM from a file located in another host.")
def migrate_scp(
    host_ip: Annotated[
        str, typer.Argument(help="IP address of the host from which to migrate a VM.")
    ],
    img_name: Annotated[str, typer.Argument(help="Name of the VM to run")],
):
    try:
        run_vm_scp(host_ip, img_name)
    except Exception as e:
        print(e)


@app.command(help="Create a VM using NFS")
def create_vm(
    img_name: Annotated[
        str, typer.Argument(help="Name of the vm image type (for example: ubuntu20.04)")
    ],
    image_path: Annotated[
        str,
        typer.Argument(
            help="Path to image file or link to iso. If not provided, it will be downloaded.",
        ),
    ],
    vm_name: Annotated[str, typer.Argument(help="Name of the VM")],
    disk_size: Annotated[
        int, typer.Option("--disk-size", "-d", help="Disk size in GB")
    ] = 10,
    ram_size: Annotated[
        int, typer.Option("--ram-size", "-r", help="RAM size in MB")
    ] = 1024,
):
    create_vm_on_nfs(vm_name, image_path, img_name, disk_size, ram_size)


@app.command(help="Delete VM")
def delete_vm(
    vm_name: Annotated[str, typer.Argument(help="Name of the VM to delete")],
):
    delete_nfs_vm(vm_name)


@app.command(help="Migrate lical VM live")
def migrate_local_live(
    vm_name: Annotated[str, typer.Argument(help="Name of the VM to migrate")],
    host_ip: Annotated[
        str, typer.Argument(help="IP address of the host where vw is currently running")
    ],
):
    migrate_live_local(vm_name, host_ip)


@app.command(help="Migrate lical VM live")
def migrate_nfs_live(
    vm_name: Annotated[str, typer.Argument(help="Name of the VM to migrate")],
    host_ip: Annotated[
        str, typer.Argument(help="IP address of the host where vw is currently running")
    ],
    host_nfs_path: Annotated[str, typer.Argument(help="NFS path on the host")],
):
    migrate_live_nfs(vm_name, host_ip, host_nfs_path)


if __name__ == "__main__":
    app()
