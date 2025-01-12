.. _SDOC_DD:

Design Document
$$$$$$$$$$$$$$$

This document describes the architecture and the implementation details of StrictDoc. Compared to the User Guide that describes how to use StrictDoc, this Design Document focuses on the "how it works" of StrictDoc.

Overview
========

StrictDoc consists of two applications:

1. StrictDoc command-line application (CLI).
2. StrictDoc web application.

Both applications share a significant subset of the backend and frontend logic. The backend logic is written in Python, the frontend logic is written using HTML/CSS, Jinja templates, and a combination of Turbo.js/Stimulus.js frontend libraries.

Building blocks
===============

StrictDoc is based on the following open-source libraries and tools:

.. list-table::
   :header-rows: 1
   :widths: 15 85

   * - **Library/tool**
     - **Description**

   * - TextX
     - Used for StrictDoc grammar definition and parsing of the sdoc files.

   * - Jinja
     - Rendering HTML templates.

   * - Sphinx and Docutils
     - - Support of Restructured Text (reST) format
       - Generation of RST documents into HTML
       - Generation of RST documents into PDF using LaTeX
       - Generating documentation websites using Sphinx.

   * - FastAPI
     - Server used for StrictDoc's Web-based user interface.

   * - Turbo and Stimulus
     - Javascript frameworks used for StrictDoc's Web-based user interface.

   * - Selenium and SeleniumBase
     - Used for end-to-end testing of StrictDoc's Web-based user interface.

.. _SECTION-DD-High-level-architecture:

High-level architecture
=======================

The following diagram captures the high-level architecture of StrictDoc.

.. image:: _assets/StrictDoc_Architecture.drawio.png
   :alt: StrictDoc's architecture diagram
   :class: image
   :width: 100%

StrictDoc command-line application
==================================

StrictDoc command-line application is at the core of StrictDoc. The command-line interface contains commands for exporting/importing SDoc content from/to other formats and presenting documentation content to a user.

The command-line application can be seen as a Model-View-Controller application:

- A command entered by a user gets recognized by the CLI arguments parser.
- Depending on the type of command, a responsible Action (Controller layer) processes the command (export action, import action, etc.).
- The input of the command is transformed by the action using the backend (Model layer) (SDoc, ReqIF, Excel, etc.).
- The resulting output is written back to HTML or other formats (View layer).

StrictDoc web application
=========================

StrictDoc Web application is based on FastAPI / Uvicorn. The end-to-end usage cycle of the web application is as follows:

- A browser requests documents from a FastAPI server.
- The FastAPI web server parses the SDoc files into memory and converts them into HTML using Jinja templates. The resulting HTML output is given back to the user.
- The Jinja templates are extended with JavaScript logic that allows a user to edit the documents and send the updated content back to the server.
- The server writes the updated content back to the SDoc files stored on a user's file system.

The HTML Over the Wire (Hotwire) architecture
---------------------------------------------

StrictDoc uses the `Hotwire architecture <https://hotwired.dev>`_.

The JavaScript framework used by StrictDoc is minimized to Turbo.js/Stimulus.js which helps to avoid the complexity of the larger JS frameworks such as React, Vue, Angular, etc. In accordance with the Hotwire approach, most of the StrictDoc's business logic is done on a server, while Turbo and Stimulus provide a thin layer of JS and AJAX to connect the almost static HTML with the server.

The Hotwire approach helps to reduce the differences between the static HTML produced by the StrictDoc command-line application and the StrictDoc web application. In both cases, the core content of StrictDoc is a statically generated website with documents. The web application extends the static HTML content with Turbo/Stimulus to turn it into a dynamic website.

Currently, the web server renders the HTML documents using the same generators that are used by the static HTML export, so the static HTML documentation and the web application interface look identical. The web interface adds the action buttons and other additional UI elements for editing the content.

Parsing SDoc files
==================

StrictDoc uses `textX <https://github.com/textX/textX>`_  which is a ``meta-language for building Domain-Specific Languages (DSLs) in Python``. The textX itself is based on `Arpeggio <https://github.com/textX/Arpeggio>`_ which is a ``Parser interpreter based on PEG grammars written in Python``.

StrictDoc relies on both tools to get:

- A declarative grammar description
- Automatic conversion of the parsed blocks into Python objects
- Fast parsing of SDoc files.

One important implementation detail of Arpeggio that influences StrictDoc user experience is that the parser stops immediately when it encounters an error. For a document that has several issues, the parser highlights only the first error without going any further. When the first error is resolved, the second error will be shown, etc.

HTML escaping
=============

StrictDoc uses Jinja2 autoescaping_ for HTML output. `Template.render`_ calls
will escape any Python object unless it's explicitly marked as safe.

Good to know for a start:

- If a Python object intentionally contains HTML it must be marked as safe
  to bypass autoescaping. Templates can do this by piping to safe_, or Python code
  can do it by wrapping an object into `markupsafe.Markup`_.
- Passing text to the `Markup() <markupsafe.Markup_>`_ constructor marks that text
  as safe, but *does not escape* it.
- Text can be explicitly escaped with `markupsafe.escape`_. It's similar to
  `html.escape`_, but the result is immediately marked safe.
- `markupsafe.Markup`_ is responsible for some "magic". It's a :code:`str` subclass
  with the same methods, but escaping arguments. For example,
  :code:`"> " + Markup("<div>safe</div>")` will turn into :code:`"&gt; <div>safe</div>"`,
  thanks to :code:`__radd__` in this specific case. To prevent escaping,
  you would use :code:`Markup("> ") + Markup("<div>safe</div>")`. Basically the
  same magic happens in templates when using safe_.
- See also `Working with Automatic Escaping`_.

.. _autoescaping: https://jinja.palletsprojects.com/en/latest/api/#autoescaping
.. _Working with Automatic Escaping: https://jinja.palletsprojects.com/en/latest/templates/#working-with-automatic-escaping
.. _markupsafe.Markup: https://markupsafe.palletsprojects.com/en/latest/escaping/#markupsafe.Markup
.. _markupsafe.escape: https://markupsafe.palletsprojects.com/en/latest/escaping/#markupsafe.escape
.. _safe: https://jinja.palletsprojects.com/en/latest/templates/#jinja-filters.safe
.. _Template.render: https://jinja.palletsprojects.com/en/latest/api/#jinja2.Template.render
.. _html.escape: https://docs.python.org/3/library/html.html#html.escape
