# core/ytguard.py: the upload guard shared by every channel (owner 17.11).
# Huge To Scale uploads nothing yet; the uploader, when it comes, calls check_channel, all_uploads,
# find_existing with ref("hugetoscale", slug), taken_days and persist - see the docstring.
