# Google Drive Maintenance

This program will traverse all files and folders in Google Drive and add/remove
collaborators to ensure that the list matches a provided list of shared people.

For files owned by a different user, the file can be copied and the old file
deleted.

## Required Software

* Python 2.7 or above
* Pip package manager

## Setup

1. Create new project and enable Google Drive API access from
[Google Developers Console](https://console.developers.google.com/apis/dashboard).
2. Create an OAuth 2.0 API key (any ID and product name works that doesn't have
the word "Google" in it), and save as `client_id.json`
3. Run `pip install -R requirements.txt` to install dependencies.
4. Run program

```bash
# Example: Take ownership of files, disable link sharing, and remove all collaborators (set only yourself as collaborator):
python gdrivemaintenance.py "WE Bots" -c webots@eng.uwo.ca -t -l

```

## Usage

```bash
usage: gdrivemaintenance.py [-h] [--collaborators email [email ...]]
                            [--take-ownership] [--disable-links] [--what-if]
                            [--version]
                            [folder]

Update sharing and ownership permissions on Google Drive files/folders to
match a predefined list.

positional arguments:
  folder                The folder to recursively start changing sharing and
                        ownership.

optional arguments:
  -h, --help            show this help message and exit
  --collaborators email [email ...], -c email [email ...]
                        the collaborators that should exist on the
                        files/folders. If blank, stops sharing.
  --take-ownership, -t  should files/folders have their ownership changed
  --disable-links, -l   Disable all sharing by links
  --what-if             shows what would happen, without actually executing
                        changes to Google Drive
  --version             show program's version number and exit

```