# Chat_Exporter
An alpha-stage Python exporter for turning shared ChatGPT conversations into clean, readable Markdown — built to preserve the strange little details other parsers might throw away.

## What it does

ChatExporter takes a public ChatGPT **Share URL**, reads the underlying conversation structure, reconstructs the active conversation branch, and exports the dialogue as a Markdown file.

It currently:

* preserves both user and assistant messages
* reconstructs the selected conversation path
* supports multiple ChatGPT text content structures, including `text` and `multimodal_text`
* preserves Markdown formatting and citation markers where possible
* creates a clean `.md` transcript
* copies a rich-text version to the macOS clipboard for easy pasting into places such as Medium or Substack

## Why I made it

I wanted a simple way to preserve long ChatGPT conversations as readable documents.

During development I discovered that ChatGPT conversations contain more structural variety than is immediately visible in the browser. An early version of ChatExporter discarded content types it did not recognise — and consequently managed to delete a perfectly visible assistant response from the exported transcript.

That bug led to a useful design principle:

> **Preserve first. Interpret second.**

The current version is deliberately becoming more tolerant of unfamiliar conversation structures rather than assuming that anything it does not understand is irrelevant.

## Status

⚠️ **Alpha software**

ChatExporter currently works with the shared ChatGPT conversations I have tested, but ChatGPT's internal page structure is not a stable public API and may change without warning.

Expect bugs, missing edge cases, mysterious content types, and possibly undiscovered species living in the conversation graph.

If you find one, please open an issue. 🕵️

## Requirements

ChatExporter currently requires:

* Python 3
* `requests`
* `markdown`
* `pyobjc` / `AppKit`

The rich-text clipboard feature currently makes this version **macOS-specific**.

The core conversation extraction code itself is not inherently Mac-specific, so separating the exporter from the clipboard functionality is a likely future improvement.

## Installation

Clone the repository:

```bash
git clone [<https://github.com/Jenion-seven/Chat_Exporter.git>]
cd ChatExporter
```

Create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the dependencies:

```bash
pip install requests markdown pyobjc
```

## Usage

Run:

```bash
python3 export_chat.py
```

ChatExporter will ask for a public ChatGPT Share URL:

```text
Paste ChatGPT Share URL:
```

For example:

```text
https://chatgpt.com/share/...
```

The conversation will be downloaded and exported as a Markdown file in the current directory.

A rich-text version is also copied to the macOS clipboard.

## Known limitations

* Only public ChatGPT Share URLs are currently supported.
* ChatGPT's internal conversation format may change.
* Some unusual or newly introduced content structures may not yet be recognised.
* Clipboard support currently depends on macOS `AppKit`.
* Conversation branches and edited/regenerated responses have only had limited testing.
* This has not yet been tested across a large range of old and new ChatGPT conversations.

## Philosophy

One of the accidental lessons of building this project was that an unknown data structure should not automatically be treated as junk.

In other words:

```python
if content_type != "what_we_expect":
    # maybe don't delete it just yet
```

ChatExporter is gradually being developed around the assumption that **unknown means unresolved, not irrelevant**.

## Contributions

Contributions, experiments, bug reports and strange conversation specimens are very welcome.

Particularly useful areas include:

* testing different generations of ChatGPT shared conversations
* identifying additional content types
* improving handling of structured or multimodal messages
* Windows and Linux clipboard/output support
* better preservation of links, citations and embedded material
* tests and example fixtures
* making the parser more resilient to future ChatGPT changes

If ChatExporter eats part of your conversation, please open an issue and describe what disappeared.

## License

MIT License.

See `LICENSE` for details.
