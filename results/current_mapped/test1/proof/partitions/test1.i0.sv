module miter (
  input  [ 11:0] \__pi_I0__15_4 ,
  input  [ 11:0] \__pi_I1__15_4 ,
  input  [ 11:0] \__pi_I2__15_4 ,
  input  [ 11:0] \__pi_I3__15_4 ,
  input  [ 11:0] \__pi_I4__15_4 ,
  input  [ 11:0] \__pi_I5__15_4 ,
  input  [ 11:0] \__pi_I6__15_4 ,
  input  [ 11:0] \__pi_I7__15_4 ,
  input  [ 11:0] \__pi_Q0__15_4 ,
  input  [ 11:0] \__pi_Q1__15_4 ,
  input  [ 11:0] \__pi_Q2__15_4 ,
  input  [ 11:0] \__pi_Q3__15_4 ,
  input  [ 11:0] \__pi_Q4__15_4 ,
  input  [ 11:0] \__pi_Q5__15_4 ,
  input  [ 11:0] \__pi_Q6__15_4 ,
  input  [ 11:0] \__pi_Q7__15_4 ,
  input  [  0:0] \__pi_clock ,
  input  [  0:0] \__pi_reset ,
  input  [  0:0] \__pi_valid ,
`ifdef DIRECT_CROSS_POINTS
`else
`endif
  output [ 11:0] \__po_i0__gold ,
  output [ 11:0] \__po_i1__gold ,
  output [ 11:0] \__po_i2__gold ,
  output [ 11:0] \__po_i3__gold ,
  output [ 11:0] \__po_i4__gold ,
  output [ 11:0] \__po_i5__gold ,
  output [ 11:0] \__po_i6__gold ,
  output [ 11:0] \__po_i7__gold ,
  output [  0:0] \__po_inter0007_out__gold ,
  output [ 11:0] \__po_inter0008_out__gold ,
  output [ 11:0] \__po_inter0009_out__gold ,
  output [  0:0] \__po_por6_out__gold ,
  output [ 11:0] \__po_q0__gold ,
  output [ 11:0] \__po_q1__gold ,
  output [ 11:0] \__po_q2__gold ,
  output [ 11:0] \__po_q3__gold ,
  output [ 11:0] \__po_q4__gold ,
  output [ 11:0] \__po_q5__gold ,
  output [ 11:0] \__po_q6__gold ,
  output [ 11:0] \__po_q7__gold ,
  output [  3:0] \__po_state__gold ,
  output [ 11:0] \__po_i0__gate ,
  output [ 11:0] \__po_i1__gate ,
  output [ 11:0] \__po_i2__gate ,
  output [ 11:0] \__po_i3__gate ,
  output [ 11:0] \__po_i4__gate ,
  output [ 11:0] \__po_i5__gate ,
  output [ 11:0] \__po_i6__gate ,
  output [ 11:0] \__po_i7__gate ,
  output [  0:0] \__po_inter0007_out__gate ,
  output [ 11:0] \__po_inter0008_out__gate ,
  output [ 11:0] \__po_inter0009_out__gate ,
  output [  0:0] \__po_por6_out__gate ,
  output [ 11:0] \__po_q0__gate ,
  output [ 11:0] \__po_q1__gate ,
  output [ 11:0] \__po_q2__gate ,
  output [ 11:0] \__po_q3__gate ,
  output [ 11:0] \__po_q4__gate ,
  output [ 11:0] \__po_q5__gate ,
  output [ 11:0] \__po_q6__gate ,
  output [ 11:0] \__po_q7__gate ,
  output [  3:0] \__po_state__gate
);
  \gold.test1.i0 gold (
    .\__pi_I0__15_4 (\__pi_I0__15_4 ),
    .\__pi_I1__15_4 (\__pi_I1__15_4 ),
    .\__pi_I2__15_4 (\__pi_I2__15_4 ),
    .\__pi_I3__15_4 (\__pi_I3__15_4 ),
    .\__pi_I4__15_4 (\__pi_I4__15_4 ),
    .\__pi_I5__15_4 (\__pi_I5__15_4 ),
    .\__pi_I6__15_4 (\__pi_I6__15_4 ),
    .\__pi_I7__15_4 (\__pi_I7__15_4 ),
    .\__pi_Q0__15_4 (\__pi_Q0__15_4 ),
    .\__pi_Q1__15_4 (\__pi_Q1__15_4 ),
    .\__pi_Q2__15_4 (\__pi_Q2__15_4 ),
    .\__pi_Q3__15_4 (\__pi_Q3__15_4 ),
    .\__pi_Q4__15_4 (\__pi_Q4__15_4 ),
    .\__pi_Q5__15_4 (\__pi_Q5__15_4 ),
    .\__pi_Q6__15_4 (\__pi_Q6__15_4 ),
    .\__pi_Q7__15_4 (\__pi_Q7__15_4 ),
    .\__pi_clock (\__pi_clock ),
    .\__pi_reset (\__pi_reset ),
    .\__pi_valid (\__pi_valid ),
`ifdef DIRECT_CROSS_POINTS
`else
`endif
    .\__po_i0 (\__po_i0__gold ),
    .\__po_i1 (\__po_i1__gold ),
    .\__po_i2 (\__po_i2__gold ),
    .\__po_i3 (\__po_i3__gold ),
    .\__po_i4 (\__po_i4__gold ),
    .\__po_i5 (\__po_i5__gold ),
    .\__po_i6 (\__po_i6__gold ),
    .\__po_i7 (\__po_i7__gold ),
    .\__po_inter0007_out (\__po_inter0007_out__gold ),
    .\__po_inter0008_out (\__po_inter0008_out__gold ),
    .\__po_inter0009_out (\__po_inter0009_out__gold ),
    .\__po_por6_out (\__po_por6_out__gold ),
    .\__po_q0 (\__po_q0__gold ),
    .\__po_q1 (\__po_q1__gold ),
    .\__po_q2 (\__po_q2__gold ),
    .\__po_q3 (\__po_q3__gold ),
    .\__po_q4 (\__po_q4__gold ),
    .\__po_q5 (\__po_q5__gold ),
    .\__po_q6 (\__po_q6__gold ),
    .\__po_q7 (\__po_q7__gold ),
    .\__po_state (\__po_state__gold )
  );
  \gate.test1.i0 gate (
    .\__pi_I0__15_4 (\__pi_I0__15_4 ),
    .\__pi_I1__15_4 (\__pi_I1__15_4 ),
    .\__pi_I2__15_4 (\__pi_I2__15_4 ),
    .\__pi_I3__15_4 (\__pi_I3__15_4 ),
    .\__pi_I4__15_4 (\__pi_I4__15_4 ),
    .\__pi_I5__15_4 (\__pi_I5__15_4 ),
    .\__pi_I6__15_4 (\__pi_I6__15_4 ),
    .\__pi_I7__15_4 (\__pi_I7__15_4 ),
    .\__pi_Q0__15_4 (\__pi_Q0__15_4 ),
    .\__pi_Q1__15_4 (\__pi_Q1__15_4 ),
    .\__pi_Q2__15_4 (\__pi_Q2__15_4 ),
    .\__pi_Q3__15_4 (\__pi_Q3__15_4 ),
    .\__pi_Q4__15_4 (\__pi_Q4__15_4 ),
    .\__pi_Q5__15_4 (\__pi_Q5__15_4 ),
    .\__pi_Q6__15_4 (\__pi_Q6__15_4 ),
    .\__pi_Q7__15_4 (\__pi_Q7__15_4 ),
    .\__pi_clock (\__pi_clock ),
    .\__pi_reset (\__pi_reset ),
    .\__pi_valid (\__pi_valid ),
`ifdef DIRECT_CROSS_POINTS
`else
`endif
    .\__po_i0 (\__po_i0__gate ),
    .\__po_i1 (\__po_i1__gate ),
    .\__po_i2 (\__po_i2__gate ),
    .\__po_i3 (\__po_i3__gate ),
    .\__po_i4 (\__po_i4__gate ),
    .\__po_i5 (\__po_i5__gate ),
    .\__po_i6 (\__po_i6__gate ),
    .\__po_i7 (\__po_i7__gate ),
    .\__po_inter0007_out (\__po_inter0007_out__gate ),
    .\__po_inter0008_out (\__po_inter0008_out__gate ),
    .\__po_inter0009_out (\__po_inter0009_out__gate ),
    .\__po_por6_out (\__po_por6_out__gate ),
    .\__po_q0 (\__po_q0__gate ),
    .\__po_q1 (\__po_q1__gate ),
    .\__po_q2 (\__po_q2__gate ),
    .\__po_q3 (\__po_q3__gate ),
    .\__po_q4 (\__po_q4__gate ),
    .\__po_q5 (\__po_q5__gate ),
    .\__po_q6 (\__po_q6__gate ),
    .\__po_q7 (\__po_q7__gate ),
    .\__po_state (\__po_state__gate )
  );
`ifdef ASSUME_DEFINED_INPUTS
  miter_def_prop #(12, "assume") \__pi_I0__15_4__assume (\__pi_I0__15_4 );
  miter_def_prop #(12, "assume") \__pi_I1__15_4__assume (\__pi_I1__15_4 );
  miter_def_prop #(12, "assume") \__pi_I2__15_4__assume (\__pi_I2__15_4 );
  miter_def_prop #(12, "assume") \__pi_I3__15_4__assume (\__pi_I3__15_4 );
  miter_def_prop #(12, "assume") \__pi_I4__15_4__assume (\__pi_I4__15_4 );
  miter_def_prop #(12, "assume") \__pi_I5__15_4__assume (\__pi_I5__15_4 );
  miter_def_prop #(12, "assume") \__pi_I6__15_4__assume (\__pi_I6__15_4 );
  miter_def_prop #(12, "assume") \__pi_I7__15_4__assume (\__pi_I7__15_4 );
  miter_def_prop #(12, "assume") \__pi_Q0__15_4__assume (\__pi_Q0__15_4 );
  miter_def_prop #(12, "assume") \__pi_Q1__15_4__assume (\__pi_Q1__15_4 );
  miter_def_prop #(12, "assume") \__pi_Q2__15_4__assume (\__pi_Q2__15_4 );
  miter_def_prop #(12, "assume") \__pi_Q3__15_4__assume (\__pi_Q3__15_4 );
  miter_def_prop #(12, "assume") \__pi_Q4__15_4__assume (\__pi_Q4__15_4 );
  miter_def_prop #(12, "assume") \__pi_Q5__15_4__assume (\__pi_Q5__15_4 );
  miter_def_prop #(12, "assume") \__pi_Q6__15_4__assume (\__pi_Q6__15_4 );
  miter_def_prop #(12, "assume") \__pi_Q7__15_4__assume (\__pi_Q7__15_4 );
  miter_def_prop #(1, "assume") \__pi_clock__assume (\__pi_clock );
  miter_def_prop #(1, "assume") \__pi_reset__assume (\__pi_reset );
  miter_def_prop #(1, "assume") \__pi_valid__assume (\__pi_valid );
`endif
`ifndef DIRECT_CROSS_POINTS
`endif
`ifdef CHECK_MATCH_POINTS
`endif
`ifdef CHECK_OUTPUTS
  miter_cmp_prop #(12, "assert") \__po_i0__assert (\__po_i0__gold , \__po_i0__gate );
  miter_cmp_prop #(12, "assert") \__po_i1__assert (\__po_i1__gold , \__po_i1__gate );
  miter_cmp_prop #(12, "assert") \__po_i2__assert (\__po_i2__gold , \__po_i2__gate );
  miter_cmp_prop #(12, "assert") \__po_i3__assert (\__po_i3__gold , \__po_i3__gate );
  miter_cmp_prop #(12, "assert") \__po_i4__assert (\__po_i4__gold , \__po_i4__gate );
  miter_cmp_prop #(12, "assert") \__po_i5__assert (\__po_i5__gold , \__po_i5__gate );
  miter_cmp_prop #(12, "assert") \__po_i6__assert (\__po_i6__gold , \__po_i6__gate );
  miter_cmp_prop #(12, "assert") \__po_i7__assert (\__po_i7__gold , \__po_i7__gate );
  miter_cmp_prop #(1, "assert") \__po_inter0007_out__assert (\__po_inter0007_out__gold , \__po_inter0007_out__gate );
  miter_cmp_prop #(12, "assert") \__po_inter0008_out__assert (\__po_inter0008_out__gold , \__po_inter0008_out__gate );
  miter_cmp_prop #(12, "assert") \__po_inter0009_out__assert (\__po_inter0009_out__gold , \__po_inter0009_out__gate );
  miter_cmp_prop #(1, "assert") \__po_por6_out__assert (\__po_por6_out__gold , \__po_por6_out__gate );
  miter_cmp_prop #(12, "assert") \__po_q0__assert (\__po_q0__gold , \__po_q0__gate );
  miter_cmp_prop #(12, "assert") \__po_q1__assert (\__po_q1__gold , \__po_q1__gate );
  miter_cmp_prop #(12, "assert") \__po_q2__assert (\__po_q2__gold , \__po_q2__gate );
  miter_cmp_prop #(12, "assert") \__po_q3__assert (\__po_q3__gold , \__po_q3__gate );
  miter_cmp_prop #(12, "assert") \__po_q4__assert (\__po_q4__gold , \__po_q4__gate );
  miter_cmp_prop #(12, "assert") \__po_q5__assert (\__po_q5__gold , \__po_q5__gate );
  miter_cmp_prop #(12, "assert") \__po_q6__assert (\__po_q6__gold , \__po_q6__gate );
  miter_cmp_prop #(12, "assert") \__po_q7__assert (\__po_q7__gold , \__po_q7__gate );
  miter_cmp_prop #(4, "assert") \__po_state__assert (\__po_state__gold , \__po_state__gate );
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
  miter_def_prop #(12, "cover") \__po_i0__gold_cover (\__po_i0__gold );
  miter_def_prop #(12, "cover") \__po_i1__gold_cover (\__po_i1__gold );
  miter_def_prop #(12, "cover") \__po_i2__gold_cover (\__po_i2__gold );
  miter_def_prop #(12, "cover") \__po_i3__gold_cover (\__po_i3__gold );
  miter_def_prop #(12, "cover") \__po_i4__gold_cover (\__po_i4__gold );
  miter_def_prop #(12, "cover") \__po_i5__gold_cover (\__po_i5__gold );
  miter_def_prop #(12, "cover") \__po_i6__gold_cover (\__po_i6__gold );
  miter_def_prop #(12, "cover") \__po_i7__gold_cover (\__po_i7__gold );
  miter_def_prop #(1, "cover") \__po_inter0007_out__gold_cover (\__po_inter0007_out__gold );
  miter_def_prop #(12, "cover") \__po_inter0008_out__gold_cover (\__po_inter0008_out__gold );
  miter_def_prop #(12, "cover") \__po_inter0009_out__gold_cover (\__po_inter0009_out__gold );
  miter_def_prop #(1, "cover") \__po_por6_out__gold_cover (\__po_por6_out__gold );
  miter_def_prop #(12, "cover") \__po_q0__gold_cover (\__po_q0__gold );
  miter_def_prop #(12, "cover") \__po_q1__gold_cover (\__po_q1__gold );
  miter_def_prop #(12, "cover") \__po_q2__gold_cover (\__po_q2__gold );
  miter_def_prop #(12, "cover") \__po_q3__gold_cover (\__po_q3__gold );
  miter_def_prop #(12, "cover") \__po_q4__gold_cover (\__po_q4__gold );
  miter_def_prop #(12, "cover") \__po_q5__gold_cover (\__po_q5__gold );
  miter_def_prop #(12, "cover") \__po_q6__gold_cover (\__po_q6__gold );
  miter_def_prop #(12, "cover") \__po_q7__gold_cover (\__po_q7__gold );
  miter_def_prop #(4, "cover") \__po_state__gold_cover (\__po_state__gold );
`endif
`ifdef COVER_DEF_GATE_OUTPUTS
  miter_def_prop #(12, "cover") \__po_i0__gate_cover (\__po_i0__gate );
  miter_def_prop #(12, "cover") \__po_i1__gate_cover (\__po_i1__gate );
  miter_def_prop #(12, "cover") \__po_i2__gate_cover (\__po_i2__gate );
  miter_def_prop #(12, "cover") \__po_i3__gate_cover (\__po_i3__gate );
  miter_def_prop #(12, "cover") \__po_i4__gate_cover (\__po_i4__gate );
  miter_def_prop #(12, "cover") \__po_i5__gate_cover (\__po_i5__gate );
  miter_def_prop #(12, "cover") \__po_i6__gate_cover (\__po_i6__gate );
  miter_def_prop #(12, "cover") \__po_i7__gate_cover (\__po_i7__gate );
  miter_def_prop #(1, "cover") \__po_inter0007_out__gate_cover (\__po_inter0007_out__gate );
  miter_def_prop #(12, "cover") \__po_inter0008_out__gate_cover (\__po_inter0008_out__gate );
  miter_def_prop #(12, "cover") \__po_inter0009_out__gate_cover (\__po_inter0009_out__gate );
  miter_def_prop #(1, "cover") \__po_por6_out__gate_cover (\__po_por6_out__gate );
  miter_def_prop #(12, "cover") \__po_q0__gate_cover (\__po_q0__gate );
  miter_def_prop #(12, "cover") \__po_q1__gate_cover (\__po_q1__gate );
  miter_def_prop #(12, "cover") \__po_q2__gate_cover (\__po_q2__gate );
  miter_def_prop #(12, "cover") \__po_q3__gate_cover (\__po_q3__gate );
  miter_def_prop #(12, "cover") \__po_q4__gate_cover (\__po_q4__gate );
  miter_def_prop #(12, "cover") \__po_q5__gate_cover (\__po_q5__gate );
  miter_def_prop #(12, "cover") \__po_q6__gate_cover (\__po_q6__gate );
  miter_def_prop #(12, "cover") \__po_q7__gate_cover (\__po_q7__gate );
  miter_def_prop #(4, "cover") \__po_state__gate_cover (\__po_state__gate );
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
module \gold.test1.i0 (
  input  [ 11:0] \__pi_I0__15_4 ,
  input  [ 11:0] \__pi_I1__15_4 ,
  input  [ 11:0] \__pi_I2__15_4 ,
  input  [ 11:0] \__pi_I3__15_4 ,
  input  [ 11:0] \__pi_I4__15_4 ,
  input  [ 11:0] \__pi_I5__15_4 ,
  input  [ 11:0] \__pi_I6__15_4 ,
  input  [ 11:0] \__pi_I7__15_4 ,
  input  [ 11:0] \__pi_Q0__15_4 ,
  input  [ 11:0] \__pi_Q1__15_4 ,
  input  [ 11:0] \__pi_Q2__15_4 ,
  input  [ 11:0] \__pi_Q3__15_4 ,
  input  [ 11:0] \__pi_Q4__15_4 ,
  input  [ 11:0] \__pi_Q5__15_4 ,
  input  [ 11:0] \__pi_Q6__15_4 ,
  input  [ 11:0] \__pi_Q7__15_4 ,
  input  [  0:0] \__pi_clock ,
  input  [  0:0] \__pi_reset ,
  input  [  0:0] \__pi_valid ,
  output [ 11:0] \__po_i0 ,
  output [ 11:0] \__po_i1 ,
  output [ 11:0] \__po_i2 ,
  output [ 11:0] \__po_i3 ,
  output [ 11:0] \__po_i4 ,
  output [ 11:0] \__po_i5 ,
  output [ 11:0] \__po_i6 ,
  output [ 11:0] \__po_i7 ,
  output [  0:0] \__po_inter0007_out ,
  output [ 11:0] \__po_inter0008_out ,
  output [ 11:0] \__po_inter0009_out ,
  output [  0:0] \__po_por6_out ,
  output [ 11:0] \__po_q0 ,
  output [ 11:0] \__po_q1 ,
  output [ 11:0] \__po_q2 ,
  output [ 11:0] \__po_q3 ,
  output [ 11:0] \__po_q4 ,
  output [ 11:0] \__po_q5 ,
  output [ 11:0] \__po_q6 ,
  output [ 11:0] \__po_q7 ,
  output [  3:0] \__po_state
);
endmodule
module \gate.test1.i0 (
  input  [ 11:0] \__pi_I0__15_4 ,
  input  [ 11:0] \__pi_I1__15_4 ,
  input  [ 11:0] \__pi_I2__15_4 ,
  input  [ 11:0] \__pi_I3__15_4 ,
  input  [ 11:0] \__pi_I4__15_4 ,
  input  [ 11:0] \__pi_I5__15_4 ,
  input  [ 11:0] \__pi_I6__15_4 ,
  input  [ 11:0] \__pi_I7__15_4 ,
  input  [ 11:0] \__pi_Q0__15_4 ,
  input  [ 11:0] \__pi_Q1__15_4 ,
  input  [ 11:0] \__pi_Q2__15_4 ,
  input  [ 11:0] \__pi_Q3__15_4 ,
  input  [ 11:0] \__pi_Q4__15_4 ,
  input  [ 11:0] \__pi_Q5__15_4 ,
  input  [ 11:0] \__pi_Q6__15_4 ,
  input  [ 11:0] \__pi_Q7__15_4 ,
  input  [  0:0] \__pi_clock ,
  input  [  0:0] \__pi_reset ,
  input  [  0:0] \__pi_valid ,
  output [ 11:0] \__po_i0 ,
  output [ 11:0] \__po_i1 ,
  output [ 11:0] \__po_i2 ,
  output [ 11:0] \__po_i3 ,
  output [ 11:0] \__po_i4 ,
  output [ 11:0] \__po_i5 ,
  output [ 11:0] \__po_i6 ,
  output [ 11:0] \__po_i7 ,
  output [  0:0] \__po_inter0007_out ,
  output [ 11:0] \__po_inter0008_out ,
  output [ 11:0] \__po_inter0009_out ,
  output [  0:0] \__po_por6_out ,
  output [ 11:0] \__po_q0 ,
  output [ 11:0] \__po_q1 ,
  output [ 11:0] \__po_q2 ,
  output [ 11:0] \__po_q3 ,
  output [ 11:0] \__po_q4 ,
  output [ 11:0] \__po_q5 ,
  output [ 11:0] \__po_q6 ,
  output [ 11:0] \__po_q7 ,
  output [  3:0] \__po_state
);
endmodule
