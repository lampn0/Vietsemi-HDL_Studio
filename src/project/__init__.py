"""Projects and libraries.

    hdp.py        read / write the .hdp project file (INI-like, same format as the legacy tool)
    project.py    Project / Library / DesignUnit / View objects, scanning of library folders
    generate.py   generate the HDL file of a view into its library's hdl folder
    lock.py       edit locks (<file>.lck, legacy format) so two users never edit one view
    templates.py  the content of new design units (FSM, Verilog / SystemVerilog module)
"""
