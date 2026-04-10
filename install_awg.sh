#! /bin/bash

sudo mkdir -p /etc/amnezia/amneziawg
sudo cp ~/amnezia_for_awg.conf /etc/amnezia/amneziawg/wg0.conf
sudo add-apt-repository ppa:amnezia/ppa
sudo apt install -y software-properties-common python3-launchpadlib gnupg2 linux-headers-$(uname -r)
sudo apt install -y amneziawg
sudo awg setconf wg0 /etc/amnezia/amneziawg/wg0.conf
sudo systemctl enable --now awg-quick@wg0
