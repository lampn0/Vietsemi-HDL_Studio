# examples

Example projects (`<project>.hdp` next to its libraries). Open one with File > Open Project,
or `python bin/hdlstudio.py examples/uart_studio/uart.hdp`.

| Project | What it is |
|---|---|
| `uart_studio/` | a UART built with HDL Studio: two state diagrams (`uart_tx`, `uart_rx`, saved as `.fsm.json`), a hand-written `baud_gen.v` and a block diagram `uart_top` (`.bd.json`), with the HDL generated from them. |

The `.hdp` file names a shared project through a team path variable; when the variable is not
set the Design Manager only reports it in the Log.
