# g2g

A django app to copy data between internal and external git repo's under control.

A simple django app with a add/edit/delete and index page for each model (like admin)

The configuration is done in xauto and the templates are global to the project currently

## models

We currently have:

Git2Git
 - `Server`: the git servers we know about.
 - `Url`: the git urls we know, must relate to Server. (Repo?)
 - `UrlPair`: defined source and target and the copy type, relates to `Url` and `CopyType`.
 - `CopyType`: how do we copy, automatic, manual, do we maybe need an explicit tag, relates to `Script`.
 - `Script`: a script we can use to copy between git repo's, may relate to a `Url`.

Components
 - `Component`: a program or library having features and having its own repo (url)
 - `Feature`: a feature on a component that needs/is implemented
 - `Implementation`: keep track of what feature is implemented on what component
 - `Dependencies`: what component uses what other component

### TODO

 - `Run`: trigger a manual copy action with parameters.

## Index

All index pages can search and filter on each fields using the input fields under the name row.

### filter

Filter fields are defind in xauth per model, fk fields use <fieldname>__name to seach on the fk name.

All filter fields currently use only icontains.

## Add/Edit/Delete

The form for defining instances is reused for edit and delete (as readonly)

## Layout

The current layout is based on bootstrap 5.3.x , but is very simple otherwise while still developing.

## Generic Views

### AUTO_GUI

Each app can define a file `autoGui.py` where hints are stored for the `genericForm` and `genericIndex`.
This alows for a very fast insert/update/delete/search to be implemented per app,
 (based on the models used) that can still be overridden if needed.
