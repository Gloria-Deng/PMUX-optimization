module miter (
  input  [  7:0] \__pi_a0 ,
  input  [  7:0] \__pi_a1 ,
  input  [  7:0] \__pi_a2 ,
  input  [  7:0] \__pi_a3 ,
  input  [  7:0] \__pi_b0 ,
  input  [  7:0] \__pi_b1 ,
  input  [  7:0] \__pi_b2 ,
  input  [  7:0] \__pi_b3 ,
  input  [  1:0] \__pi_s ,
`ifdef DIRECT_CROSS_POINTS
`else
`endif
  output [  3:0] \__po_y__gold ,
  output [  3:0] \__po_y__gate
);
  \gold.signed_sub_truncated gold (
    .\__pi_a0 (\__pi_a0 ),
    .\__pi_a1 (\__pi_a1 ),
    .\__pi_a2 (\__pi_a2 ),
    .\__pi_a3 (\__pi_a3 ),
    .\__pi_b0 (\__pi_b0 ),
    .\__pi_b1 (\__pi_b1 ),
    .\__pi_b2 (\__pi_b2 ),
    .\__pi_b3 (\__pi_b3 ),
    .\__pi_s (\__pi_s ),
`ifdef DIRECT_CROSS_POINTS
`else
`endif
    .\__po_y (\__po_y__gold )
  );
  \gate.signed_sub_truncated gate (
    .\__pi_a0 (\__pi_a0 ),
    .\__pi_a1 (\__pi_a1 ),
    .\__pi_a2 (\__pi_a2 ),
    .\__pi_a3 (\__pi_a3 ),
    .\__pi_b0 (\__pi_b0 ),
    .\__pi_b1 (\__pi_b1 ),
    .\__pi_b2 (\__pi_b2 ),
    .\__pi_b3 (\__pi_b3 ),
    .\__pi_s (\__pi_s ),
`ifdef DIRECT_CROSS_POINTS
`else
`endif
    .\__po_y (\__po_y__gate )
  );
`ifdef ASSUME_DEFINED_INPUTS
  miter_def_prop #(8, "assume") \__pi_a0__assume (\__pi_a0 );
  miter_def_prop #(8, "assume") \__pi_a1__assume (\__pi_a1 );
  miter_def_prop #(8, "assume") \__pi_a2__assume (\__pi_a2 );
  miter_def_prop #(8, "assume") \__pi_a3__assume (\__pi_a3 );
  miter_def_prop #(8, "assume") \__pi_b0__assume (\__pi_b0 );
  miter_def_prop #(8, "assume") \__pi_b1__assume (\__pi_b1 );
  miter_def_prop #(8, "assume") \__pi_b2__assume (\__pi_b2 );
  miter_def_prop #(8, "assume") \__pi_b3__assume (\__pi_b3 );
  miter_def_prop #(2, "assume") \__pi_s__assume (\__pi_s );
`endif
`ifndef DIRECT_CROSS_POINTS
`endif
`ifdef CHECK_MATCH_POINTS
`endif
`ifdef CHECK_OUTPUTS
  miter_cmp_prop #(4, "assert") \__po_y__assert (\__po_y__gold , \__po_y__gate );
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
  miter_def_prop #(4, "cover") \__po_y__gold_cover (\__po_y__gold );
`endif
`ifdef COVER_DEF_GATE_OUTPUTS
  miter_def_prop #(4, "cover") \__po_y__gate_cover (\__po_y__gate );
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
module \gold.signed_sub_truncated (
  input  [  7:0] \__pi_a0 ,
  input  [  7:0] \__pi_a1 ,
  input  [  7:0] \__pi_a2 ,
  input  [  7:0] \__pi_a3 ,
  input  [  7:0] \__pi_b0 ,
  input  [  7:0] \__pi_b1 ,
  input  [  7:0] \__pi_b2 ,
  input  [  7:0] \__pi_b3 ,
  input  [  1:0] \__pi_s ,
  output [  3:0] \__po_y
);
endmodule
module \gate.signed_sub_truncated (
  input  [  7:0] \__pi_a0 ,
  input  [  7:0] \__pi_a1 ,
  input  [  7:0] \__pi_a2 ,
  input  [  7:0] \__pi_a3 ,
  input  [  7:0] \__pi_b0 ,
  input  [  7:0] \__pi_b1 ,
  input  [  7:0] \__pi_b2 ,
  input  [  7:0] \__pi_b3 ,
  input  [  1:0] \__pi_s ,
  output [  3:0] \__po_y
);
endmodule
