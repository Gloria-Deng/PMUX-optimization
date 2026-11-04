module shared_upstream_cones(input [7:0] a,b,c,d,
    input [1:0] s,t, input [127:0] wide, output [127:0] untouched,
    output reg [7:0] y);
    wire [7:0] u=(a^b)+(c&d);
    wire [7:0] v=(a&c)^(b|d);
    wire [7:0] p=u^v;
    assign untouched=wide^{16{p}};
    always @* case(s)
    0:y=(u^a)+(v^b);
    1:y=(u^b)+(v^c);
    2:y=(u^c)+(v^d);
    default:y=(u^d)+(v^a);
    endcase
    endmodule
    