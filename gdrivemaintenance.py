#! /usr/bin/env python3

import sys
import argparse
from GoogleDriveOperations import GoogleDriveOperations, google_pager, EnhancedBatchHttpRequest
import googleapiclient.errors


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
    parser = argparse.ArgumentParser(description="Update sharing and ownership permissions on Google Drive"
                                                 " files/folders to match a predefined list.")
    parser.add_argument("folder", type=str, nargs="?", default="WE Bots",
                        help="The folder to recursively start changing sharing and ownership.")
    parser.add_argument("--collaborators", "-c", metavar="email", type=str, nargs="+", action="append", default=[],
                        help="the collaborators that should exist on the files/folders."
                             " If blank, removes all collaborators.")
    parser.add_argument("--take-ownership", "-t", action="store_true", default=False,
                        help="should files/folders have their ownership changed")
    parser.add_argument("--disable-links", "-l", action="store_true", default=False,
                        help="Disable all sharing by links")
    parser.add_argument("--what-if", action="store_true", default=False,
                        help="shows what would happen, without actually executing changes to Google Drive")
    parser.add_argument("--version", action="version", version="%(prog)s {0}".format(version))

    args = parser.parse_args()

    # Flatten collaborators and convert to set
    args.collaborators = set([item for sublist in args.collaborators for item in sublist])
    return args


def perm_edit_callback(id, response, exception):
    if exception is not None:
        print("Batch execution callback failed:", file=sys.stderr)
        print(exception, file=sys.stderr)


def modify_permissions(api_client, file_resource, collaborators, disable_links, what_if, permissions=None, batch=None):
    """Edits permissions on a file owned by the executor to match the 'collaborators' preference.

    :param api_client: The Google API object wrapper to interact with
    :param file_resource: The file to modify permissions for.
    :param collaborators: Collaborators allowed on the file.
    :param disable_links: Should a shared link be disabled?
    :param what_if: Should permission modification happen, or just print what would happen?
    :param permissions: The file's permissions. Will be retrieved fresh if blank.
    :param batch: Object to use for batching permission edits, if provided.
    :return: None
    """
    batch_internal = api_client.service.new_batch_http_request(perm_edit_callback)  # Batch at the file level or higher

    # If permissions aren't already supplied, retrieve them
    if permissions is None:
        permissions = api_client.get_permissions(file_resource)

    # Delete unwanted permissions as specified by the requested state
    for perm in permissions:
        if perm["id"] == "anyoneWithLink":
            # Check that link disabling is requested
            if not disable_links:
                return

            api_client.delete_permission(file_resource,
                                         perm,
                                         what_if,
                                         batch if batch is not None else batch_internal)
        elif perm["emailAddress"] not in collaborators:
            api_client.delete_permission(file_resource,
                                         perm,
                                         what_if,
                                         batch if batch is not None else batch_internal)

    # Add wanted permissions as specified by requested state
    wanted_collaborators = collaborators
    existing_collaborators = set([perm["emailAddress"] for perm in permissions if "emailAddress" in perm])
    missing_collaborators = wanted_collaborators - existing_collaborators

    for collab_email in missing_collaborators:
        api_client.add_permission(file_resource,
                                  collab_email,
                                  what_if,
                                  batch=batch if batch is not None else batch_internal)

    if batch is None:
        batch_internal.execute()     # Bulk-delete sharing edits on this file if not batching at a higher level


def main():

    # Step 1: Get all files and folders
    # Step 2: Copy objects that don't belong to executor, move sub-objects if needed, and delete old objects
    # Step 3: Restrict sharing

    args = argument_parsing()
    try:
        ops = GoogleDriveOperations(args.folder)
    except FileNotFoundError:
        print("Folder '{0}' not found. Exiting...".format(args.folder), file=sys.stderr)
        sys.exit(1)

    # Add current user to collaborators if not present
    if ops.userinfo.emailAddress not in args.collaborators:
        args.collaborators.add(ops.userinfo.emailAddress)

    # Call the Drive v3 API to get all files for processing
    print("Fixing owners and sharing permissions in files and folders...")
    file_request = ops.service.files().list(pageSize=1000, q=ops.subfolder_filter,
                                            fields="nextPageToken," + GoogleDriveOperations.STD_FIELDS_LIST)

    # Batch all the permission changes, since they don't have dependencies
    perm_batch = EnhancedBatchHttpRequest(ops.service, callback=lambda rid, resp, error: print(error, file=sys.stderr))

    for drive_obj in google_pager(file_request, "files", ops.service.files().list_next):
        # Fix ownership if desired, then fix permissions
        try:
            if not ops.is_owner(drive_obj) and args.take_ownership:
                drive_obj = ops.take_ownership(drive_obj, args.what_if)

            if drive_obj is not None:   # None is possible when "What-If" is requested

                # If the ownership changes are not requested, add the owner to the allowed collaborators list
                aug_collaborators = set(args.collaborators)
                if not args.take_ownership:
                    aug_collaborators.add(ops.get_owner_email(drive_obj))

                modify_permissions(ops,
                                   drive_obj,
                                   aug_collaborators,
                                   args.disable_links,
                                   args.what_if,
                                   batch=perm_batch)
        except googleapiclient.errors.HttpError as err:
            print("Error modifying state for '{0}', skipping...".format(drive_obj["name"]), file=sys.stderr)
            print(err, file=sys.stderr)

    # Execute all permission changes
    perm_batch.execute()


if __name__ == "__main__":
    main()
