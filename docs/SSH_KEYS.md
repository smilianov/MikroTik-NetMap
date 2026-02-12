# SSH Key Authentication for MikroTik-NetMap

MikroTik-NetMap supports SSH key-based authentication as an alternative to
password-based API access. This is more secure — no passwords are stored in
config files or environment variables.

## Overview

Three connection modes are available per device:

| Mode      | Port | Auth             | RouterOS Version |
|-----------|------|------------------|------------------|
| `rest`    | 443  | Username/password | 7.1+            |
| `classic` | 8728 | Username/password | 6.49+           |
| `ssh`     | 22   | SSH key or password | Any            |

## Step 1: Generate an SSH Key Pair

On the machine running MikroTik-NetMap (or your workstation):

```bash
# Ed25519 (recommended — smallest, fastest)
ssh-keygen -t ed25519 -f netmap_key -C "netmap-monitoring" -N ""

# Or RSA 4096-bit (wider compatibility)
ssh-keygen -t rsa -b 4096 -f netmap_key -C "netmap-monitoring" -N ""
```

This creates two files:
- `netmap_key` — private key (keep this secure, never share)
- `netmap_key.pub` — public key (upload to MikroTik devices)

## Step 2: Import the Public Key to MikroTik

### Option A: Via WinBox / WebFig

1. Open **System → Users**
2. Select the user (e.g., `admin` or a dedicated `netmap` user)
3. Click **SSH Keys** tab
4. Click **Import SSH Key**
5. Upload the `netmap_key.pub` file

### Option B: Via SSH / Terminal

```bash
# Copy the public key to the device
scp netmap_key.pub admin@10.0.0.1:/

# SSH into the device
ssh admin@10.0.0.1

# Import the key for the user
/user/ssh-keys/import public-key-file=netmap_key.pub user=admin

# Verify
/user/ssh-keys/print
```

### Option C: Mass Deployment via Script

```bash
# Deploy to multiple devices at once
for IP in 10.0.0.1 10.0.0.2 10.0.0.3; do
  scp netmap_key.pub admin@${IP}:/
  ssh admin@${IP} "/user/ssh-keys/import public-key-file=netmap_key.pub user=admin"
  echo "Done: ${IP}"
done
```

## Step 3: Create a Dedicated Monitoring User (Recommended)

For security, create a read-only user on each MikroTik device:

```
/user/group/add name=netmap-ro policy=read,api,ssh,!write,!ftp,!reboot,!policy,!sensitive,!sniff,!test,!password

/user/add name=netmap group=netmap-ro

/user/ssh-keys/import public-key-file=netmap_key.pub user=netmap
```

This user can:
- Read interface stats, neighbor tables, and system resources
- Connect via SSH and API
- Cannot modify any configuration

## Step 4: Configure MikroTik-NetMap

Place the private key file where the application can access it:

```bash
# For Docker deployment:
mkdir -p config/ssh_keys
cp netmap_key config/ssh_keys/id_ed25519
chmod 600 config/ssh_keys/id_ed25519
```

Update `config/netmap.yaml`:

```yaml
devices:
  - name: core-router
    host: 10.0.0.1
    type: router
    api_type: ssh
    username: netmap        # or admin
    ssh_key_file: /app/config/ssh_keys/id_ed25519
    position: {x: 400, y: 200}

  # You can mix SSH and password-based devices:
  - name: old-router
    host: 10.0.0.2
    type: router
    api_type: classic
    password: "${OLD_ROUTER_PASS}"
    position: {x: 400, y: 400}
```

### Docker Volume Mount

When running in Docker, ensure the SSH keys directory is mounted:

```bash
docker run -d --name netmap \
  -p 8585:8585 \
  -v /path/to/config:/app/config \
  netmap
```

The key file path in `netmap.yaml` should use the container path
(e.g., `/app/config/ssh_keys/id_ed25519`).

## Step 5: Test the Connection

```bash
# Test SSH access manually first
ssh -i netmap_key -o StrictHostKeyChecking=no netmap@10.0.0.1 "/ip/neighbor/print terse"
```

If you see neighbor output, the SSH key is working correctly.

## Security Best Practices

1. **Use Ed25519 keys** — smaller, faster, and more secure than RSA
2. **No passphrase** on the key file — the app runs unattended
3. **Read-only user** — limit what the monitoring account can do
4. **File permissions** — `chmod 600` on the private key
5. **Separate key per deployment** — don't reuse keys across projects
6. **Rotate keys periodically** — regenerate and re-deploy annually

## Troubleshooting

### "SSH key file not found"
Check that the path in `ssh_key_file` is correct and accessible inside the
Docker container. Use `docker exec netmap ls -la /app/config/ssh_keys/` to
verify.

### "Permission denied (publickey)"
- Verify the public key is imported for the correct user on the MikroTik device
- Check that the username in `netmap.yaml` matches the MikroTik user
- Ensure SSH is enabled: `/ip/service/set ssh disabled=no`

### "Connection refused on port 22"
Enable SSH on the device:
```
/ip/service/set ssh disabled=no port=22
```

### "Host key verification failed"
MikroTik-NetMap disables strict host key checking by default. If you see this
error, the SSH library may have cached an old host key. Delete
`~/.ssh/known_hosts` entries for the device.
