import requests
import re
import json
from pathlib import Path
from urllib.parse import urlparse
import markdown as md_lib
from AppKit import (
    NSPasteboard,
    NSPasteboardTypeHTML,
    NSPasteboardTypeString,
)


# ==================================================
# ChatExporter 0.3
# Export a single ChatGPT shared conversation
# to Markdown.
# ==================================================


def download_page(url):
    response = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    response.raise_for_status()
    return response.text



def extract_router_data(html):
    pattern = (
        r'window\.__reactRouterContext\.streamController'
        r'\.enqueue\("(.+?)"\);'
    )

    matches = re.findall(
        pattern,
        html,
        flags=re.DOTALL
    )

    if not matches:
        raise RuntimeError(
            "Could not find ChatGPT conversation data "
            "in the shared page."
        )

    candidates = []

    for block in matches:
        try:
            decoded = json.loads(f'"{block}"')
        except json.JSONDecodeError:
            continue

        try:
            parsed = json.loads(decoded)
        except (json.JSONDecodeError, TypeError):
            continue

        # The conversation payload is normally
        # a large flattened list.
        if isinstance(parsed, list):
            candidates.append(parsed)

    if not candidates:
        raise RuntimeError(
            "Found ChatGPT page data, but could not "
            "identify a conversation payload."
        )

    # Do not assume the conversation is the first block.
    # Choose the largest flattened data table.
    data = max(
        candidates,
        key=len
    )

    return data



def make_helpers(data):

    def decode_key(key):
        if isinstance(key, str) and key.startswith("_"):
            number = key[1:]

            if number.isdigit():
                index = int(number)

                if 0 <= index < len(data):
                    return data[index]

        return key


    def deref(value):
        if (
            isinstance(value, int)
            and not isinstance(value, bool)
            and 0 <= value < len(data)
        ):
            return data[value]

        return value


    def decode_dict(obj):
        if not isinstance(obj, dict):
            return {}

        result = {}

        for raw_key, value in obj.items():
            real_key = decode_key(raw_key)

            if isinstance(real_key, str):
                result[real_key] = value

        return result


    def get_field(obj, field_name):
        if not isinstance(obj, dict):
            return None

        for raw_key, value in obj.items():
            if decode_key(raw_key) == field_name:
                return deref(value)

        return None


    return decode_key, deref, decode_dict, get_field


def build_nodes(data, decode_dict, deref):
    nodes = {}

    for index, item in enumerate(data):

        if not isinstance(item, dict):
            continue

        decoded = decode_dict(item)

        required = {
            "id",
            "message",
            "parent",
            "children",
        }

        if not required.issubset(decoded.keys()):
            continue

        node_id = deref(decoded["id"])

        if not isinstance(node_id, str):
            continue

        nodes[node_id] = {
            "table_index": index,
            "message_ref": decoded["message"],
            "parent": deref(decoded["parent"]),
            "children": deref(decoded["children"]),
        }

    return nodes


def find_conversation_info(
    data,
    nodes,
    decode_dict,
    deref
):
    """
    Find the conversation-level object.

    Returns:
        current_node
        title
    """

    for item in data:

        if not isinstance(item, dict):
            continue

        decoded = decode_dict(item)

        if "current_node" not in decoded:
            continue

        current_node = deref(
            decoded["current_node"]
        )

        if current_node not in nodes:
            continue

        title = None

        if "title" in decoded:
            candidate = deref(
                decoded["title"]
            )

            if isinstance(candidate, str):
                title = candidate.strip()

        return current_node, title

    return None, None


def build_active_path(nodes, current_node):
    """
    Walk backwards from current_node through parent
    links, then reverse the result.

    This reconstructs the selected conversation branch.
    """

    ordered = []
    visited = set()

    node_id = current_node

    while node_id in nodes:

        if node_id in visited:
            raise RuntimeError(
                "A loop was detected in the conversation graph."
            )

        visited.add(node_id)

        node = nodes[node_id]
        ordered.append(node)

        parent = node["parent"]

        if not parent or parent not in nodes:
            break

        node_id = parent

    ordered.reverse()

    return ordered


def fallback_linear_path(nodes):
    """
    Used only if current_node cannot be found.
    Works well for conversations without branches.
    """

    roots = [
        node_id
        for node_id, node in nodes.items()
        if (
            node["parent"] is None
            or node["parent"] not in nodes
        )
    ]

    if len(roots) != 1:
        raise RuntimeError(
            "Could not determine a unique conversation path."
        )

    ordered = []
    visited = set()

    current_id = roots[0]

    while current_id in nodes:

        if current_id in visited:
            raise RuntimeError(
                "A loop was detected in the conversation graph."
            )

        visited.add(current_id)

        node = nodes[current_id]
        ordered.append(node)

        children = node["children"]

        if not children:
            break

        next_child = children[0]

        if isinstance(next_child, int):
            # Usually children contains strings already,
            # but leave this fallback harmless.
            break

        current_id = next_child

    return ordered


def get_role(message, get_field):
    author = get_field(
        message,
        "author"
    )

    if not isinstance(author, dict):
        return None

    return get_field(
        author,
        "role"
    )


def get_text(
    message,
    get_field,
    deref
):
    """
    Extract visible textual content from ChatGPT messages.

    ChatGPT shared conversations do not always store visible prose as
    content_type == "text" with plain-string parts. Newer messages may
    use "multimodal_text" and may wrap text inside dictionaries.
    """

    content = get_field(
        message,
        "content"
    )

    if not isinstance(content, dict):
        return None

    content_type = get_field(
        content,
        "content_type"
    )

    # These are the two normal containers that can carry visible prose.
    if content_type not in (
        "text",
        "multimodal_text",
    ):
        return None

    texts = []

    parts = get_field(
        content,
        "parts"
    )

    if isinstance(parts, list):
        for part_ref in parts:
            part = deref(part_ref)

            if isinstance(part, str):
                texts.append(part)
                continue

            # Multimodal text parts may be represented as dictionaries.
            if isinstance(part, dict):
                part_text = get_field(
                    part,
                    "text"
                )

                if isinstance(part_text, str):
                    texts.append(part_text)

    # Some content objects expose their prose directly as a text field.
    direct_text = get_field(
        content,
        "text"
    )

    if isinstance(direct_text, str):
        if direct_text not in texts:
            texts.append(direct_text)

    texts = [
        text
        for text in texts
        if isinstance(text, str) and text.strip()
    ]

    if not texts:
        return None

    return "\n".join(texts)


def clean_text(text):
    """
    Conservative cleaning.

    ChatExporter 0.1 deliberately preserves things
    such as ChatGPT citation markers because they may
    contain useful information.

    We remove only artefacts that we already know are
    not part of the visible conversation.
    """

    text = text.strip()

    if text == (
        "Original custom instructions "
        "no longer available"
    ):
        return ""

    return text


def extract_messages(
    ordered_nodes,
    deref,
    get_field
):
    messages = []

    for node in ordered_nodes:

        message = deref(
            node["message_ref"]
        )

        if not isinstance(message, dict):
            continue

        role = get_role(
            message,
            get_field
        )

        if role not in (
            "user",
            "assistant",
        ):
            continue

        text = get_text(
            message,
            get_field,
            deref
        )

        if not text:
            continue

        text = clean_text(text)

        if not text:
            continue

        messages.append(
            {
                "role": role,
                "text": text,
            }
        )

    return messages


def make_markdown(messages):
    output = []

    for message in messages:

        if message["role"] == "user":
            speaker = "Jennifer"
        else:
            speaker = "ChatGPT"

        output.append(
            f"## {speaker}"
        )

        output.append("")
        output.append(
            message["text"]
        )
        output.append("")

    return "\n".join(output).rstrip() + "\n"


def make_filename(title, url):
    """
    Create a safe Markdown filename from
    the conversation title.
    """

    if title:
        filename = title
    else:
        path = urlparse(url).path.rstrip("/")
        filename = path.split("/")[-1]

    # Remove characters that are awkward or illegal
    # in filenames.
    filename = re.sub(
        r'[\\/:*?"<>|]',
        '',
        filename
    )

    # Collapse whitespace
    filename = re.sub(
        r'\s+',
        ' ',
        filename
    ).strip()

    if not filename:
        filename = "ChatGPT Conversation"

    return f"{filename}.md"



def copy_rich_text_to_clipboard(markdown_text):
    """
    Convert Markdown into HTML and place both
    rich HTML and plain text onto the macOS clipboard.
    """

    html = md_lib.markdown(
        markdown_text,
        extensions=[
            "fenced_code",
            "tables",
        ]
    )

    # Wrap it as a small HTML document
    html_document = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
</head>
<body>
{html}
</body>
</html>
""".strip()

    pasteboard = NSPasteboard.generalPasteboard()
    pasteboard.clearContents()

    # Rich-text version for apps such as Substack
    pasteboard.setString_forType_(
        html_document,
        NSPasteboardTypeHTML
    )

    # Plain Markdown fallback
    pasteboard.setString_forType_(
        markdown_text,
        NSPasteboardTypeString
    )


# ==================== main =========================

def main():

    print()
    print("ChatExporter 0.3")
    print("----------------")
    print()

    url = input(
        "Paste ChatGPT Share URL: "
    ).strip()

    if not url:
        print("No URL supplied.")
        return

    if "chatgpt.com/share/" not in url:
        print(
            "That doesn't look like a "
            "ChatGPT Share URL."
        )
        return

    try:

        print("\nReading conversation...")

        html = download_page(url)

        data = extract_router_data(html)

        (
            decode_key,
            deref,
            decode_dict,
            get_field,
        ) = make_helpers(data)

        nodes = build_nodes(
            data,
            decode_dict,
            deref
        )

        if not nodes:
            raise RuntimeError(
                "No conversation nodes were found."
            )

        
        current_node, title = find_conversation_info(
            data,
            nodes,
            decode_dict,
            deref
        )



        if current_node:
            ordered_nodes = build_active_path(
                nodes,
                current_node
            )
        else:
            ordered_nodes = fallback_linear_path(
                nodes
            )

        messages = extract_messages(
            ordered_nodes,
            deref,
            get_field
        )

        if not messages:
            raise RuntimeError(
                "No user or assistant messages were found."
        )

        markdown = make_markdown(
            messages
        )

                
        filename = make_filename(
            title,
            url
        )
        

        output_path = (
            Path.cwd() / filename
        )

        output_path.write_text(
            markdown,
            encoding="utf-8"
        )
        
        
        copy_rich_text_to_clipboard(
            markdown
        )

        
        print()
        print(
            f"Exported {len(messages)} messages."
        )
        
        print(
            f"Saved: {output_path.name}"
        )
        
        print(
            "Copied Substack-ready rich text to clipboard."
        )
        
        print()



    except requests.RequestException as error:

        print()
        print(
            "Could not download the shared conversation."
        )
        print(error)

    except (
        RuntimeError,
        json.JSONDecodeError,
    ) as error:

        print()
        print(
            "Could not export conversation:"
        )
        print(error)


if __name__ == "__main__":
    main()
    
    


