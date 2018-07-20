#! /usr/bin/env python

from __future__ import print_function
from apiclient.discovery import build
import googleapiclient.errors
from httplib2 import Http
from oauth2client import file, client, tools
import sys

import argparse


SCOPES = 'https://www.googleapis.com/auth/drive'
ACCOUNT = "webots@eng.uwo.ca"
STD_FIELDS = "files(name,id,parents,owners)"

# TODO: Restucture
SERVICE = None
ARGS = None
USERINFO = None
FOLDER_IDS = set()


def setup():
    """Handles initializing the Google Drive API authentication.

    :return: Authenticated Google Drive API service object
    """
    # Setup the Drive v3 API
    store = file.Storage('token.json')
    creds = store.get()
    if not creds or creds.invalid:
        flow = client.flow_from_clientsecrets('client_id.json', SCOPES, login_hint=ACCOUNT)
        creds = tools.run_flow(flow, store)
    return build('drive', 'v3', http=creds.authorize(Http()))


def version_extraction():
    """Provides the version number of the program from the VERSION file.

    :return: Version number as a string
    """
    with open("VERSION", "r") as vers:
        return vers.read()


def argument_parsing():
    """Parses command line arguments, and provides help text, if desired.

    :return: Parsed arguments
    """
    version = version_extraction()
    parser = argparse.ArgumentParser(description='Update sharing and ownership permissions on Google Drive'
                                                 ' files/folders to match a predefined list.')
    parser.add_argument('folder', type=str, nargs='?', default='WE Bots',
                        help='The folder to recursively start changing sharing and ownership.')
    parser.add_argument('--collaborators', '-c', metavar='email', type=str, nargs='+', action="append", default=[],
                        help='the collaborators that should exist on the files/folders. If blank, stops sharing.')
    parser.add_argument('--take-ownership', '-t', action='store_true', default=False,
                        help='should files/folders have their ownership changed')
    parser.add_argument('--disable-links', '-l', action='store_true', default=False,
                        help='Disable all sharing by links')
    parser.add_argument('--what-if', action='store_true', default=False,
                        help='shows what would happen, without actually executing changes to Google Drive')
    parser.add_argument('--version', action='version', version='%(prog)s {0}'.format(version))

    args = parser.parse_args()

    # Flatten collaborators
    args.collaborators = [item for sublist in args.collaborators for item in sublist]
    return args


def get_permissions(file_resource):
    """Get all permissions for a file.

    :param file_resource: The file to query permissions for.
    :return: All permissions on the file.
    """
    permissions = []

    perm_request = SERVICE.permissions().list(fileId=file_resource['id'], fields="permissions(id,emailAddress,role)")
    while perm_request is not None:
        results = perm_request.execute()

        permissions.extend(results.get("permissions", []))
        perm_request = SERVICE.permissions().list_next(perm_request, results)

    return permissions


def is_owner(file_resource):
    """Checks if the current user owns the file.

    :param file_resource: The file to check the owner of.
    :return: True if current user owns the file
    """
    owners = None

    # Get permissions if not in original request
    if 'owners' not in file_resource:
        owners = SERVICE.files().get(fileId=file_resource['id'],
                                     fields="nextPageToken," + STD_FIELDS)\
            .execute().get('owners', [])
    else:
        owners = file_resource.get('owners', [])

    for owner in owners:
        if owner['permissionId'] == USERINFO['permissionId']:
            return True
    return False


def delete_permission(file_resource, perm, batch=None):
    """Given a file and and a permission, deletes it.

    :param file_resource: The file containing the permission
    :param perm: The permission to delete
    :param batch: Object to add the deletion to. Otherwise execute deletion immediately.
    :return: None
    """
    file_name = file_resource['name']

    try:
        command = SERVICE.permissions().delete(fileId=file_resource['id'], permissionId=perm['id'])

        if batch is None:
            command.execute()
        else:
            batch.add(command)
    except googleapiclient.errors.HttpError as err:
        if err.resp.status == 404:
            print('File "{0}" not found.'.format(file_name), file=sys.stderr)
        elif err.resp.status == 403:
            print('Permission denied to edit file "{0}".'.format(file_name), file=sys.stderr)
        else:
            print(err, file=sys.stderr)


def cleanup_permission(perm, file_resource, batch=None):
    """Decides the action to take on individual permissions, batching if desired.

    :param perm: The permission to be cleaned up.
    :param file_resource: The file that contains the permission.
    :param batch: (Optional) The batch object to use for bulk-cleanup, if provided.
    :return: None
    """
    file_name = file_resource['name']

    if perm['id'] == 'anyoneWithLink':
        if ARGS.disable_links:
            msg = 'Disabling link for "{0}"'.format(file_name)

            if not ARGS.what_if:
                print(msg)
                delete_permission(file_resource, perm, batch)
            else:
                print("What-If: {0}".format(msg))
    elif perm['emailAddress'] not in ARGS.collaborators and perm['emailAddress'] != USERINFO['emailAddress']:
        msg = 'Deleting access to "{0}" for "{1}".'.format(file_name, perm['emailAddress'])
        if not ARGS.what_if:
            print(msg)
            delete_permission(file_resource, perm, batch)
        else:
            print("What-If: {0}".format(msg))


def perm_edit_callback(id, response, exception):
    print(exception, file=sys.stderr)


def modify_permissions(file_resource, permissions=None, batch=None):
    """Edits permissions on a file owned by the executor to match the 'collaborators' preference.

    :param file_resource: The file to modify permissions for.
    :param permissions: The file's permissions. Will be retrieved fresh if blank.
    :param batch: Object to use for batching permission edits, if provided.
    :return: None
    """
    batch_internal = SERVICE.new_batch_http_request(perm_edit_callback)  # Batch at the page or file level

    if permissions is None:
        permissions = get_permissions(file_resource)

    for perm in permissions:
        cleanup_permission(perm, file_resource, batch if batch is not None else batch_internal)

    if batch is None:
        batch_internal.execute()     # Bulk-delete sharing edits on this file if not batching at page level


def take_ownership_file(drive_file):
    """Takes ownership of a file by creating a copy, and removing the original from the folder.

    :param drive_file: The file to take ownership of.
    :return: a new drive_file object representing the new file.
    """
    msg = 'Taking ownership of file "{0}"'.format(drive_file['name'])
    if ARGS.what_if:
        print("What-If: {0}".format(msg))
        return

    print(msg)

    # Determine parents to remove from original file
    parents = set(drive_file['parents'])
    par_to_remove = [item for item in parents.intersection(FOLDER_IDS)]

    # Copy file to same places, and remove the old file from the folder tree
    new_file_results = SERVICE.files().copy(fileId=drive_file['id'], body={'parents': par_to_remove}).execute()
    new_file_meta = SERVICE.files().get(fileId=new_file_results['id'], fields=STD_FIELDS).execute()
    SERVICE.files.update(fileId=drive_file['id'], removeParents=par_to_remove).execute()

    return new_file_meta


def take_ownership_folder(drive_folder):
    """Takes ownership of a folder by creating a copy, moving all files to new folder, and removing the original.

        :param drive_folder: The folder to take ownership of.
        :return: a new drive_folder object representing the new folder.
        """
    msg = 'Taking ownership of folder "{0}"'.format(drive_folder['name'])
    if ARGS.what_if:
        print("What-If: {0}".format(msg))
        return

    print(msg)

    # Determine parents to remove from original file
    parents = set(drive_folder['parents'])
    par_in_top = [item for item in parents.intersection(FOLDER_IDS)]

    # Copy folder to same places
    new_folder_results = SERVICE.files().copy(fileId=drive_folder['id'], body={'parents': par_in_top}).execute()
    new_folder_meta = SERVICE.files().get(fileId=new_folder_results['id'], fields=STD_FIELDS).execute()

    # Move all files in old folder to new folder
    file_request = SERVICE.files().list(pageSize=1000,
                                        q="'{0}' in parents".format(drive_folder['id']),
                                        fields="nextPageToken," + STD_FIELDS)
    while file_request is not None:
        results = file_request.execute()
        drive_files = results.get('files', [])

        for drive_file in drive_files:
            SERVICE.files().update(fileId=drive_file['id'], addParents=new_folder_meta['id'], removeParents=drive_folder['id'])

        file_request = SERVICE.files().list_next(file_request, results)

    # Remove the old folder from the folder tree
    SERVICE.files.update(fileId=drive_folder['id'], removeParents=par_in_top).execute()

    return new_folder_meta


def process_file(drive_file, batch_page=None):
    try:
        if not is_owner(drive_file):
            drive_file = take_ownership_file(drive_file)

        if drive_file is not None:
            modify_permissions(drive_file, batch=batch_page)
    except googleapiclient.errors.HttpError as err:
        print('Error modifying state for "{0}", skipping...'.format(drive_file['name']))
        print(err, file=sys.stderr)


def collect_all_subfolders(top_folder_id):
    """Gathers all the IDs of the subfolders in a specified top-level folder

    :param top_folder_id: The top-level folder to get subfolders of
    :return: set of ideas of all subfolders (excluding top-level folder ID)
    """
    subfolder_ids = set()

    folder_request = SERVICE.files().list(pageSize=1000, q="mimeType = 'application/vnd.google-apps.folder' and "
                                                           "'{0}' in parents".format(top_folder_id),
                                          fields="nextPageToken,files(name,id,parents)")
    while folder_request is not None:
        results = folder_request.execute()

        drive_folders = results.get('files', [])

        for drive_folder in drive_folders:
            subfolder_ids.update(collect_all_subfolders(drive_folder['id']))
            subfolder_ids.add(drive_folder['id'])

        folder_request = SERVICE.files().list_next(folder_request, results)

    return subfolder_ids


def main():
    global ARGS
    global SERVICE
    global USERINFO
    global FOLDER_IDS

    # Setup global variables
    ARGS = argument_parsing()
    SERVICE = setup()
    USERINFO = SERVICE.about().get(fields='user(emailAddress, permissionId)').execute().get("user")

    # file_metadata = {
    #     'name': ,
    #     'mimeType': 'application/vnd.google-apps.folder'
    # }

    # Step 1: Get all files
    # Step 2: Copy files that don't belong to executor, and delete old ones (not yet)
    # Step 3: Restrict sharing
    # Step 4: Get all folders
    # Step 5: Change sharing
    # Step 6: Report folders that don't belong to executor

    # Create folder filter
    print('Scanning folders...')

    top_id = SERVICE.files().list(pageSize=1,
                                  q="mimeType = 'application/vnd.google-apps.folder' "
                                    "and name = '{0}'".format(ARGS.folder),
                                  fields="nextPageToken," + STD_FIELDS).execute()['files'][0]['id']
    folder_ids_set = collect_all_subfolders(top_id)
    folder_ids_set.add(top_id)
    FOLDER_IDS.update(folder_ids_set)
    folder_ids = ["'{0}'".format(f_id) for f_id in folder_ids_set]
    folder_filter = " in parents or ".join(folder_ids) + " in parents"
    print('Finished scanning folders')

    # Call the Drive v3 API to get all files for processing
    print('Fixing owners and sharing permissions in files...')
    file_request = SERVICE.files().list(pageSize=1000, q="mimeType != 'application/vnd.google-apps.folder'"
                                                         "and ({0})".format(folder_filter),
                                        fields="nextPageToken," + STD_FIELDS)
    while file_request is not None:
        results = file_request.execute()

        batch_page = SERVICE.new_batch_http_request(perm_edit_callback)  # Batch edits at the page level
        drive_files = results.get('files', [])

        for drive_file in drive_files:
            process_file(drive_file, batch_page)

        batch_page.execute()    # Execute all edits for the page

        file_request = SERVICE.files().list_next(file_request, results)

    # TODO: Process folders


    # if not items:
    #     print('No files found.')
    # else:
    #     print('Files:')
    #     for item in items:
    #         print('{0} ({1})'.format(item['name'], item['id']))


if __name__ == "__main__":
    main()


# Data types:
# File, folder
# Owner:
# Current user, other user
# Sharing:
# Matches share list, does not match share list
# 8 possible combinations
