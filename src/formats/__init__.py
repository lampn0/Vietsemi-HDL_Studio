"""The legacy file formats.

    sexpr.py      reader / writer of the S-expression text the legacy tool uses in .sm, .bd, .sb files
    import_sm.py  legacy state diagram (.sm) -> FsmView
    export_sm.py  FsmView -> .sm (writes the edits back into the original file)
    import_bd.py  legacy block diagram (.bd) -> BdView
    export_sb.py  symbol (.sb) writer: the ports of a unit, kept in step with its diagram
    names.py      names the legacy project format fixes (.hdp sections, path variables, folders)
"""
