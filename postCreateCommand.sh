#!/bin/bash

echo "Installing uv"
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH=/root/.local/bin:$PATH

mkdir -p /var/folders/.cache/pip

echo "Installing core feature dependencies"
uv venv --clear
uv pip install --cache-dir /var/folders/.cache/pip poetry --link-mode=copy

echo "Configuring poetry"
export PATH=/var/folders/SFTPWrangler/.venv/bin:$PATH
poetry config virtualenvs.in-project true

echo "Exporting project dependencies"
poetry self add poetry-plugin-export
poetry export -f requirements.txt > requirements.txt --with dev --without-hashes

echo "Installing project dependencies using uv/pip"
uv pip install --cache-dir /var/folders/.cache/pip -r requirements.txt --link-mode=copy

echo "Finishing poetry setup"
poetry install

echo "Setting up shell environment"
echo 'export PATH=/var/folders/SFTPWrangler/.venv/bin:/root/.local/bin:$PATH' >> /root/.bashrc
echo 'cd /var/folders/SFTPWrangler' >> /root/.bashrc
