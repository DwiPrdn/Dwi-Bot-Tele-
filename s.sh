#!/bin/bash

echo "Starting bot..."

tmux new-session -d -s bot -c "/home/whyuxxx/bokep" "sudo python3 main.py"

sleep 5

echo "Starting userbot..."

tmux new-session -d -s userbot -c "/home/whyuxxx/userkep" "sudo python3 main.py"

sleep 5

echo "Starting userbot 2..."

tmux new-session -d -s userbot2 -c "/home/whyuxxx/bokepp" "sudo python3 main.py"

sleep 3

echo "Ejet ajg"
