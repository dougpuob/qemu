"""
This is an extension to provide more configuration options to autodoc.

Showing inherited members, broadly, leads to bizarre results because it
will attempt to show inherited members for classes written outside of
the 'qemu' namespace. These classes, however, do not use ReST/Sphinx
markup, so they display ... poorly.

This extension's goal is to create a targeted list of classes we want to
show inheritance for instead. For those targeted list of classes,
attempt to remove those inherited members from the object index.
"""

changed_options_cache = {}


def change_option(name, options, key, value):
    opt_id = id(options)
    cache = changed_options_cache.setdefault(opt_id, {})
    if key not in cache:
        if key in options:
            cache[key] = options[key]
        else:
            cache[key] = '__DELETEME__'
    options[key] = value


def restore_option(name, options, key):
    opt_id = id(options)
    cache = changed_options_cache.get(opt_id, {})
    if key in cache:
        if cache[key] == '__DELETEME__':
            if key in options:
                del options[key]
        else:
            options[key] = cache[key]


def autodoc_process_docstring(app, what, name, obj, options, lines):
    if name in ('qemu.aqmp.QMPClient', 'qemu.aqmp.qmp_client.QMPClient'):
        change_option(name, options, 'inherited-members', True)
    else:
        restore_option(name, options, 'inherited-members')

    # In addition, we want to enable the 'noindex' option for things
    # that are being declared outside of their "home" location.

    # For docstrings that do not appear attached to the docstrings we are
    # forcibly turning on inherited-members for, leave the noindex
    # attribute alone, and exit.
    if not (name.startswith('qemu.aqmp.QMPClient.')
            or name.startswith('qemu.aqmp.qmp_client.QMPClient.')):
        restore_option(name, options, 'noindex')
        return

    # Otherwise, I attempt to exclude any inherited members from being
    # indexed. I am not entirely successful. :(

    modify_noindex = False

    if what == 'property':
        if not name.startswith(obj.fget.__module__):
            modify_noindex = True

    if what == 'attribute':
        # No way to determine if this is inherited or not with the information
        # we have available here. We'll have to assume it isn't.

        # For some curious reason, though, this duplicates
        # protocol.runstate_changed and QMP.runstate_changed,
        # but not protocol.name and QMP.name. *No* idea why.

        pass

    if what in ('class', 'exception', 'function', 'method'):
        if hasattr(obj, '__module__') and not name.startswith(obj.__module__):
            modify_noindex = True

    if modify_noindex:
        # print(f"noindex: {name}")
        change_option(name, options, 'noindex', True)
    else:
        restore_option(name, options, 'noindex')


def setup(sphinx):
    sphinx.connect(
        'autodoc-process-docstring',
        autodoc_process_docstring
    )
