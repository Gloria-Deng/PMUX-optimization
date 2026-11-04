module miter (
  input  [  3:0] \__pi_x ,
`ifdef DIRECT_CROSS_POINTS
`else
`endif
  output [  0:0] \__po_a__gold ,
  output [  0:0] \__po_b__gold ,
  output [  0:0] \__po_a__gate ,
  output [  0:0] \__po_b__gate
);
  \gold.decode_counterexample.a gold (
    .\__pi_x (\__pi_x ),
`ifdef DIRECT_CROSS_POINTS
`else
`endif
    .\__po_a (\__po_a__gold ),
    .\__po_b (\__po_b__gold )
  );
  \gate.decode_counterexample.a gate (
    .\__pi_x (\__pi_x ),
`ifdef DIRECT_CROSS_POINTS
`else
`endif
    .\__po_a (\__po_a__gate ),
    .\__po_b (\__po_b__gate )
  );
`ifdef ASSUME_DEFINED_INPUTS
  miter_def_prop #(4, "assume") \__pi_x__assume (\__pi_x );
`endif
`ifndef DIRECT_CROSS_POINTS
`endif
`ifdef CHECK_MATCH_POINTS
`endif
`ifdef CHECK_OUTPUTS
  miter_cmp_prop #(1, "assert") \__po_a__assert (\__po_a__gold , \__po_a__gate );
  miter_cmp_prop #(1, "assert") \__po_b__assert (\__po_b__gold , \__po_b__gate );
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
  miter_def_prop #(1, "cover") \__po_a__gold_cover (\__po_a__gold );
  miter_def_prop #(1, "cover") \__po_b__gold_cover (\__po_b__gold );
`endif
`ifdef COVER_DEF_GATE_OUTPUTS
  miter_def_prop #(1, "cover") \__po_a__gate_cover (\__po_a__gate );
  miter_def_prop #(1, "cover") \__po_b__gate_cover (\__po_b__gate );
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
module \gold.decode_counterexample.a (
  input  [  3:0] \__pi_x ,
  output [  0:0] \__po_a ,
  output [  0:0] \__po_b
);
endmodule
module \gate.decode_counterexample.a (
  input  [  3:0] \__pi_x ,
  output [  0:0] \__po_a ,
  output [  0:0] \__po_b
);
endmodule
