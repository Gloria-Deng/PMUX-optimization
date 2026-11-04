module decode_wide_counterexample(input [7:0] x, output a,b); assign a=(x==8'b00100010); assign b=(x==8'b00100011); endmodule
