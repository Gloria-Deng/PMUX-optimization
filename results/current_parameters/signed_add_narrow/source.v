module signed_add_narrow(input [1:0] s, input signed [7:0] a0, input signed [7:0] b0,
input signed [7:0] a1, input signed [7:0] b1,
input signed [7:0] a2, input signed [7:0] b2,
input signed [7:0] a3, input signed [7:0] b3, output reg signed [3:0] y);
always @* case(s)
2'd0: y = a0 + b0;
2'd1: y = a1 + b1;
2'd2: y = a2 + b2;
default: y = a3 + b3;
endcase
endmodule
