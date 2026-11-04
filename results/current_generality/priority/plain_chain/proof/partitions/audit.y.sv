module miter (
  input  [  7:0] \__pi_d0 ,
  input  [  7:0] \__pi_d1 ,
  input  [  7:0] \__pi_d2 ,
  input  [  7:0] \__pi_d3 ,
  input  [  2:0] \__pi_s ,
`ifdef DIRECT_CROSS_POINTS
`else
`endif
  output [  7:0] \__po_y__gold ,
  output [  7:0] \__po_y__gate
);
  \gold.audit.y gold (
    .\__pi_d0 (\__pi_d0 ),
    .\__pi_d1 (\__pi_d1 ),
    .\__pi_d2 (\__pi_d2 ),
    .\__pi_d3 (\__pi_d3 ),
    .\__pi_s (\__pi_s ),
`ifdef DIRECT_CROSS_POINTS
`else
`endif
    .\__po_y (\__po_y__gold )
  );
  \gate.audit.y gate (
    .\__pi_d0 (\__pi_d0 ),
    .\__pi_d1 (\__pi_d1 ),
    .\__pi_d2 (\__pi_d2 ),
    .\__pi_d3 (\__pi_d3 ),
    .\__pi_s (\__pi_s ),
`ifdef DIRECT_CROSS_POINTS
`else
`endif
    .\__po_y (\__po_y__gate )
  );
`ifdef ASSUME_DEFINED_INPUTS
  miter_def_prop #(8, "assume") \__pi_d0__assume (\__pi_d0 );
  miter_def_prop #(8, "assume") \__pi_d1__assume (\__pi_d1 );
  miter_def_prop #(8, "assume") \__pi_d2__assume (\__pi_d2 );
  miter_def_prop #(8, "assume") \__pi_d3__assume (\__pi_d3 );
  miter_def_prop #(3, "assume") \__pi_s__assume (\__pi_s );
`endif
`ifndef DIRECT_CROSS_POINTS
`endif
`ifdef CHECK_MATCH_POINTS
`endif
`ifdef CHECK_OUTPUTS
  miter_cmp_prop #(8, "assert") \__po_y__assert (\__po_y__gold , \__po_y__gate );
`endif
`ifdef COVER_DEF_CROSS_POINTS
  `ifdef DIRECT_CROSS_POINTS
  `else
  `endif
`endif
`ifdef COVER_DEF_GOLD_MATCH_POINTS
`endif
`ifdef COVER_DEF_GATE_MATCH_POINTS
`endif
`ifdef COVER_DEF_GOLD_OUTPUTS
  miter_def_prop #(8, "cover") \__po_y__gold_cover (\__po_y__gold );
`endif
`ifdef COVER_DEF_GATE_OUTPUTS
  miter_def_prop #(8, "cover") \__po_y__gate_cover (\__po_y__gate );
`endif
endmodule
module miter_cmp_prop #(parameter WIDTH=1, parameter TYPE="assert") (input [WIDTH-1:0] in_gold, in_gate);
  reg okay;
  integer i;
  always @* begin
    okay = 1;
    for (i = 0; i < WIDTH; i = i+1)
      okay = okay && (in_gold[i] === 1'bx || in_gold[i] === in_gate[i]);
  end
  generate
    if (TYPE == "assert") always @* assert(okay);
    if (TYPE == "assume") always @* assume(okay);
    if (TYPE == "cover")  always @* cover(okay);
  endgenerate
endmodule
module miter_def_prop #(parameter WIDTH=1, parameter TYPE="assert") (input [WIDTH-1:0] in);
  wire okay = ^in !== 1'bx;
  generate
    if (TYPE == "assert") always @* assert(okay);
    if (TYPE == "assume") always @* assume(okay);
    if (TYPE == "cover")  always @* cover(okay);
  endgenerate
endmodule
module \gold.audit.y (
  input  [  7:0] \__pi_d0 ,
  input  [  7:0] \__pi_d1 ,
  input  [  7:0] \__pi_d2 ,
  input  [  7:0] \__pi_d3 ,
  input  [  2:0] \__pi_s ,
  output [  7:0] \__po_y
);
endmodule
module \gate.audit.y (
  input  [  7:0] \__pi_d0 ,
  input  [  7:0] \__pi_d1 ,
  input  [  7:0] \__pi_d2 ,
  input  [  7:0] \__pi_d3 ,
  input  [  2:0] \__pi_s ,
  output [  7:0] \__po_y
);
endmodule
