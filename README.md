# Chat Exporter

**Version 0.5.4**

A small desktop utility for extracting individual ChatGPT shared conversations and converting them into clean, portable HTML or Markdown.

Chat Exporter began as a personal archiving tool: I wanted a quick way to preserve a single conversation without having to export my entire ChatGPT account history.

It has since become a small experiment in understanding how ChatGPT shared conversations are represented beneath the visible interface — including some of the mysterious citation and reference data hidden inside them. 🪲

> **Status:** Experimental / personal project.
> Chat Exporter is not affiliated with, endorsed by, or supported by OpenAI.

---

## What it does

Paste a public ChatGPT **Share URL** into Chat Exporter and the application will retrieve the shared conversation, reconstruct the active conversation path, and allow it to be exported in several forms.

The conversation can then be:

* previewed inside the app
* copied as rich HTML
* pasted directly into editors such as Substack
* saved as an HTML file
* saved as Markdown
* preserved with ChatGPTs internal reference markers intact
* processed experimentally to expose reference information

Version **0.5.4** also reconstructs supported external web citations into usable links instead of simply removing their internal ChatGPT reference markers.

---

# Features

## Direct ChatGPT Share URL loading

Paste a URL of the form:

https://chatgpt.com/share/...

and click **Fetch Chat**.

Chat Exporter downloads the shared page and extracts the conversation data embedded within it.

Fetching takes place in a background thread so the interface remains responsive while the page is being retrieved.

---

## Conversation reconstruction

ChatGPT shared pages contain considerably more information than the visible conversation.

Chat Exporter attempts to identify:

* conversation nodes
* parent/child relationships
* the currently selected conversation branch
* user messages
* assistant messages
* conversation title
* citation metadata

It then reconstructs the active path of the conversation rather than simply dumping the entire underlying data structure.

System/internal messages are excluded from the normal exported conversation.

---

## Three output modes

### 1. Clean HTML

The default publishing mode.

This removes ChatGPT-specific internal markers such as:

```text
filecite...
cite...
```

while retaining the readable conversation.

Where possible, **v0.5.4 now resolves web citation markers back into their corresponding external links**.

For example, an internal citation such as:

```text
```

may have associated citation metadata elsewhere inside the shared page.

Chat Exporter searches for that metadata and, where an appropriate human-readable alternative exists, restores the external citation/link in the exported conversation.

This makes Clean HTML particularly useful for conversations containing research sources and external references.

---

### 2. Preserve Raw

Archival / research mode.

This preserves ChatGPT reference tokens exactly as they occur in the conversation instead of hiding or interpreting them.

Examples include:

```text



```

This mode is useful when investigating ChatGPT's underlying conversation format or when you want to preserve information that future versions of Chat Exporter may learn how to interpret.

The strange little markers became affectionately known during development as the **beetles**. 🪲

Never throw away an unidentified beetle.

---

### 3. Convert Ref Data

An experimental middle ground.

Chat Exporter detects internal reference tokens and replaces them with numbered references in the text.

A reference section is then added to the end of the conversation describing the detected reference type and embedded identifiers.

Currently recognised reference families include things such as:

* web citations
* file citations
* memory citations
* other ChatGPT reference families

This feature is intentionally experimental. As more of ChatGPT's internal reference structures become understood, this mode can potentially become considerably more useful.

---

## External citation preservation — new in v0.5.4

This is the major addition in **0.5.4**.

Earlier versions could detect citation markers, but Clean HTML generally treated them as interface artefacts and removed them.

Investigation of the underlying shared-page source revealed that ChatGPT often stores additional citation records separately from the visible message text.

These can contain:

* the internal citation token
* citation type
* source metadata
* a human-readable alternative representation

Version 0.5.4 builds a citation lookup table while parsing the conversation.

When Clean HTML encounters a supported web citation, Chat Exporter attempts to replace the opaque internal marker with its corresponding readable external link.

This allows research-heavy conversations to retain much more of their original usefulness after export.

---

## Rich HTML clipboard

The **Copy HTML** button places both:

* rich HTML
* Markdown/plain-text fallback

onto the system clipboard.

Applications capable of accepting formatted clipboard data can therefore receive the rendered version directly.

This has been particularly useful for copying conversations into **Substack** while retaining:

* headings
* emphasis
* hyperlinks
* lists
* code blocks
* tables
* paragraph structure

---

## HTML export

Click:

**Download HTML**

to save the reconstructed conversation as a standalone `.html` document.

The filename is automatically derived from the original ChatGPT conversation title.

For example:

```text
Shared Reality Evidence.html
```

rather than a generic export filename.

---

## Markdown export

Click:

**Download Markdown**

to save the conversation as a `.md` file.

Markdown is useful for:

* long-term archives
* GitHub
* Obsidian and similar note systems
* static-site generators
* further text processing
* future conversion into other formats

The filename is again generated from the conversation title.

---

## Conversation preview

Before saving anything, Chat Exporter renders the reconstructed conversation in its built-in preview window.

External links in the preview are clickable.

The preview uses a white reading surface within the application's dark interface to keep long conversations comfortable to read.

---

## Smart scrolling

Long conversations create a slightly unusual interface problem: the application itself needs to scroll, but so does the conversation preview.

Chat Exporter includes a custom scrolling system designed to make these behave like one continuous document.

When scrolling downward:

1. the main interface scrolls first
2. once it reaches the conversation area, scrolling transfers naturally into the conversation preview

When scrolling upward:

1. the conversation returns to its beginning
2. scrolling then transfers back to the main interface

Trackpad pixel scrolling is supported where available.

It's a small feature, but it makes long conversations considerably nicer to navigate.

---

## Interface

Chat Exporter is currently built using **PySide6 / Qt**.

The desktop interface includes:

* dark-mode application UI
* ChatGPT Share URL field
* Fetch Chat button
* three selectable export-mode cards
* Export Chat
* Copy HTML
* Download HTML
* Download Markdown
* status/error reporting
* large conversation preview
* responsive background fetching
* smart nested scrolling

---

## Requirements

Chat Exporter requires **Python 3** and the following Python packages:

```text
PySide6
requests
markdown
```

Install them with:

```bash
python3 -m pip install PySide6 requests markdown
```

For compiling the application into a standalone executable, also install:

```bash
python3 -m pip install pyinstaller
```

---

## Running from Python source

Download or clone the project, then locate:

```text
chat_exporter_0.5.4.py
```

Open Terminal in the directory containing the file and run:

```bash
python3 chat_exporter_0.5.4.py
```

If your system uses `python` rather than `python3`, use:

```bash
python chat_exporter_0.5.4.py
```

---

## Building a macOS application

Chat Exporter can be packaged as a normal macOS `.app` using **PyInstaller**.

First install the dependencies:

```bash
python3 -m pip install PySide6 requests markdown pyinstaller
```

Then change into the folder containing the Python script:

```bash
cd /path/to/chat-exporter
```

For example:

```bash
cd ~/Desktop/ChatExporter
```

Then build the application:

```bash
python3 -m PyInstaller \
  --windowed \
  --name "Chat Exporter" \
  chat_exporter_0.5.4.py
```

PyInstaller will create several things, including:

```text
build/
dist/
Chat Exporter.spec
```

The finished application will be inside:

```text
dist/Chat Exporter.app
```

You can then launch it like a normal Mac application.

---

## Building with a custom Mac icon

If you have a macOS `.icns` icon file, place it in the same directory as the Python script.

For example:

```text
chat_exporter_0.5.4.py
ChatExporter.icns
```

Then build using:

```bash
python3 -m PyInstaller \
  --windowed \
  --name "Chat Exporter" \
  --icon "ChatExporter.icns" \
  chat_exporter_0.5.4.py
```

The resulting application will again appear at:

```text
dist/Chat Exporter.app
```

---

## Rebuilding after making changes

PyInstaller creates a `.spec` file during the first build.

For example:

```text
Chat Exporter.spec
```

This is essentially the recipe PyInstaller uses to construct the application.

For a straightforward rebuild you can simply run the original command again.

If you want to start completely clean:

```bash
rm -rf build dist
```

and then run:

```bash
python3 -m PyInstaller \
  --windowed \
  --name "Chat Exporter" \
  --icon "ChatExporter.icns" \
  chat_exporter_0.5.4.py
```

Alternatively, once the `.spec` file has been configured the way you want it, you can build directly from it:

```bash
python3 -m PyInstaller "Chat Exporter.spec"
```

---

## macOS security notice

A locally compiled application is not automatically code-signed or notarised by Apple.

Because of this, macOS may warn that the application came from an unidentified developer.

For personal or test builds, you may need to allow the application through macOS security settings.

A publicly distributed Mac application would ideally be:

* code signed
* packaged with an Apple Developer certificate
* notarised by Apple

That is outside the scope of the current experimental release.

---

## Typical workflow

1. In ChatGPT, create a **Share link** for the conversation you want to preserve.
2. Open Chat Exporter.
3. Paste the Share URL.
4. Click **Fetch Chat**.
5. Wait for the conversation title and message count to appear.
6. Select an output mode.
7. Click **Export Chat**.
8. Inspect the preview.
9. Choose **Copy HTML**, **Download HTML**, or **Download Markdown**.

For publishing to Substack, the simplest workflow is usually:

```text
Clean HTML → Export Chat → Copy HTML → Paste into Substack
```

---

## Limitations

Chat Exporter is an experimental parser, not an official ChatGPT export client.

ChatGPT's shared-page format is undocumented and may change at any time.

A future change to the structure of shared conversation pages could therefore partially or completely break the parser.

Not every internal ChatGPT reference type is currently understood.

In particular, some structures represent UI components or contextual information that cannot yet be reconstructed into their original visible form.

Rather than pretending these structures do not exist, Chat Exporter includes **Preserve Raw** specifically so that they can be retained for future investigation.

---

## Privacy and responsible use

Chat Exporter works with **ChatGPT shared conversation URLs**.

A shared link should be treated as accessible to anyone who possesses that link.

Only archive conversations that you own or otherwise have permission to access, and be careful when distributing exported conversations that may contain private or sensitive information.

Chat Exporter is intended as an experimental personal archiving and research utility.

OpenAI provides its own official account-level data export facilities. Chat Exporter is not intended to replace those facilities; its purpose is the more immediate extraction of an individual shared conversation.

---

## Project status

Chat Exporter is still very much an evolving experiment.

Current development has focused on:

* reliable extraction of the visible conversation
* clean publishing output
* preservation of hidden reference data
* reconstruction of external citations
* pleasant handling of long conversations
* learning more about the relationship between ChatGPT's visible interface and the data underneath it

Future versions may be able to interpret more of the reference structures that currently appear only in Preserve Raw mode.

The beetle hunt continues. 🪲🔬

---

## Version history

### v0.5.4

* Added reconstruction of supported external web citations
* Clean HTML can now preserve links associated with ChatGPT web citations
* Citation metadata is extracted from the shared-page data
* Existing raw-reference preservation retained
* Three export modes retained
* HTML and Markdown export
* Rich HTML clipboard support
* Conversation-title filenames
* Smart nested preview scrolling
* Background URL fetching
* PySide6 desktop interface

### v0.5.3

* Refined continuous scrolling between the application and conversation preview
* Improved behaviour for long conversations

### v0.5.x

* Native PySide6 desktop edition
* Direct ChatGPT Share URL fetching
* Built-in preview
* HTML and Markdown export
* Rich clipboard output
* Three reference-handling modes

---

## Disclaimer

Chat Exporter is an independent experimental project and is not affiliated with OpenAI or ChatGPT.

It relies on the current structure of publicly shared ChatGPT conversation pages and therefore comes with no guarantee of continued compatibility.

Use it responsibly, and expect things occasionally to break as the underlying platform evolves.

---

**Chat Exporter v0.5.4**

*Preserve the conversation. Keep the beetles.* 🪲

