yosys -import
read_verilog -sv cases/pmux_case05_nested.v
hierarchy -top pmux_case05_nested
procs
pmux_opt_rtlil -rewrite
