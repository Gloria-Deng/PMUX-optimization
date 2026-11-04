module shallow_priority(input [7:0] a,b,c,d,q, input [7:0] s, output reg [7:0] y);
reg [7:0] x0,x1,z;
always @* case(s[1:0])
0:x0=a+q;
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
always @* begin
if(s[6]) z=x0;
else if(s[7]) z=8'h12;
else z=8'h34;
end
always @* case(s[5:4])
0:y=z;
1:y=x1;
2:y=8'h00;
default:y=8'hff;
endcase
endmodule
