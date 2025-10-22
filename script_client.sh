#!/bin/bash

SERVER_IP=192.168.100.86
SHARED_DIR=/mnt/nfsshare

sudo apt update
sudo apt install nfs-common -y
sudo mkdir -p $SHARED_DIR

if ! mountpoint -q $SHARED_DIR; then
    sudo mount -t nfs $SERVER_IP:$SHARED_DIR $SHARED_DIR
    echo "Mounted $SHARED_DIR"
else
    echo "$SHARED_DIR is already mounted"
fi
