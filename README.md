# g2g
A django app to copy data between internal and external git repo's under control.

A simple django app with a add/edit/delete and index page for each model (like admin)

The configuration is done in xauto and the templates are global to the project currently

## models
We currently have:

 - `Server`: the git servers we know about.
 - `Url`: the git urls we know, must relate to Server.
 - `Script`: a script we can use to copy between git repo's, may relate to a `Url`.
 - `CopyType`: how do we copy, automatic, manual, do we maybe need an explicit tag, relates to `Script`.
 - `UrlPair`: defined source and target and the copy type, relates to `Url` and `CopyType`.

### TODO
 - `Run`: trigger a manual copy action with parameters.
