# libs - HDL libraries shipped with HDL Studio

HDL libraries that come with the tool and that projects can map, for example shared component
libraries or templates for new units.

Each library uses the usual library layout, so a project maps it like any other library:

```
libs/<library>/hdl/          Verilog / SystemVerilog source files
libs/<library>/hds/<unit>/   graphical views (fsm.sm, struct.bd, symbol.sb)
```

```
[hdl]
<library> = <path to HDL Studio>/libs/<library>/hdl
[hds]
<library> = <path to HDL Studio>/libs/<library>/hds
[library_type]
<library> = standard            ; protected: opened read-only
```

There is no shipped library yet. Python packages the tool needs are not kept here: they are
installed with `pip install -r requirements.txt`.
