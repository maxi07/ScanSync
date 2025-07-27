"""
Unified badge generation for both dashboard and live updates.
This ensures consistent badge colors across all scenarios.
"""

from scansynclib.helpers import SMB_TAG_COLORS
from scansynclib.logging import logger


def generate_badges(
    pdf_id,
    smb_target_ids,
    local_filepath,
    additional_smb_names=None,
    web_urls=None,
    remote_paths=None
):
    """
    Generate badges with consistent colors based on SMB target IDs.

    Args:
        pdf_id: PDF database ID
        smb_target_ids: List of SMB target dictionaries with 'id' key
        local_filepath: Main local file path name
        additional_smb_names: List of additional SMB names
        web_urls: List of web URLs (optional)
        remote_paths: List of remote file paths (optional)

    Returns:
        List of badge dictionaries with id, text, color, url, title
    """
    badges = []

    # Ensure defaults
    if additional_smb_names is None:
        additional_smb_names = []
    if web_urls is None:
        web_urls = []
    if remote_paths is None:
        remote_paths = []

    # Create all badges first, then sort alphabetically
    if isinstance(smb_target_ids, list) and smb_target_ids:
        # Create badge data for all targets
        all_badge_data = []

        # Add main badge data
        if smb_target_ids:
            main_target = smb_target_ids[0]
            target_id = main_target.get('id') if isinstance(main_target, dict) else main_target
            # Use text-based hash for consistent colors instead of target_id
            text_hash = hash(local_filepath or 'N/A') % len(SMB_TAG_COLORS)
            color = SMB_TAG_COLORS[text_hash]

            all_badge_data.append({
                "target_id": target_id,
                "text": local_filepath or 'N/A',
                "color": color,
                "url": web_urls[0] if web_urls else None,
                "title": remote_paths[0] if remote_paths else 'Open in OneDrive',
                "is_main": True
            })

        # Add additional badge data
        for i, target in enumerate(smb_target_ids[1:], 1):
            target_id = target.get('id') if isinstance(target, dict) else target
            text = additional_smb_names[i-1] if i-1 < len(additional_smb_names) else 'N/A'
            # Use text-based hash for consistent colors instead of target_id
            text_hash = hash(text) % len(SMB_TAG_COLORS)
            color = SMB_TAG_COLORS[text_hash]

            all_badge_data.append({
                "target_id": target_id,
                "text": text,
                "color": color,
                "url": web_urls[i] if i < len(web_urls) else None,
                "title": remote_paths[i] if i < len(remote_paths) else 'Open in OneDrive',
                "is_main": False
            })        # Sort all badges alphabetically by text
        sorted_badge_data = sorted(all_badge_data, key=lambda x: (x["text"] or "").lower())

        # Create actual badge objects in alphabetical order
        for badge_data in sorted_badge_data:
            if badge_data["is_main"]:
                badge_id = f"{pdf_id}_pdf_smb"
            else:
                # Use target_id for consistent badge IDs across sorting
                badge_id = f"{pdf_id}_badge_target_{badge_data['target_id']}"

            badge = {
                "id": badge_id,
                "text": badge_data["text"],
                "color": badge_data["color"],
                "url": badge_data["url"],
                "title": badge_data["title"]
            }
            badges.append(badge)

    logger.debug(f"Generated {len(badges)} badges for PDF {pdf_id} with sorted targets: {badges}")
    return badges
