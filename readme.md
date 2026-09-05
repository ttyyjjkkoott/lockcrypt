# LockCrypt

Simple windows desktop app for encrypting and decrypting files and folders with a password.

## Features

* Encrypt files and folders into `.7z` archives
* Decrypt `.7z` archives
* Drag and drop files
* Optional secure deletion of originals
* Simple graphical interface

## Install

Install Python 3, then:

```bash
pip install customtkinter tkinterdnd2 py7zr
```

## Run

```bash
python lockcrypt.py
```

You can also start directly in decrypt mode:

```bash
python lockcrypt.py --decrypt
```

## How to Use

1. Choose **Encrypt** or **Decrypt**.
2. Drop files/folders into the window or click to browse.
3. Enter a password.
4. Click **Encrypt** or **Decrypt**.
5. The result will be saved next to the original.

### Important

If **Securely delete originals** is enabled, the original files are deleted after processing. On SSDs, secure deletion is best-effort and cannot guarantee that the old data is unrecoverable.
