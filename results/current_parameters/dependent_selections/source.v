module dependent_selections(input [31:0] a,b,c, input [1:0] s,t, output reg [7:0] y); reg [7:0] u;
always @* case (s)
0: u = a[0 +: 8] + b[0 +: 8];
1: u = a[8 +: 8] + b[8 +: 8];
2: u = a[16 +: 8] + b[16 +: 8];
default: u = a[24 +: 8] + b[24 +: 8];
endcase
always @* case (t)
0: y = u + c[0 +: 8];
1: y = u + c[8 +: 8];
2: y = u + c[16 +: 8];
default: y = u + c[24 +: 8];
endcase
endmodule
