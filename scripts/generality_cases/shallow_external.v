module shallow_external(input [7:0] a,b,c,d,q, input [5:0] s, output reg [7:0] y, output [7:0] exposed);
wire [7:0] sum=a+q;
assign exposed=sum;
reg [7:0] x0,x1;
always @* case(s[1:0])
0:x0=sum;
1:x0=b-q;
2:x0=c+q;
default:x0=8'h5a;
endcase
always @* case(s[3:2])
0:x1=a^q;
1:x1=b|d;
2:x1=c&d;
default:x1=8'ha5;
endcase
always @* case(s[5:4])
0:y=x0;
1:y=x1;
2:y=8'h00;
default:y=8'hff;
endcase
endmodule
