module variant_indirect_result(input [5:0] x,a,b,c,input [5:0] s,output reg [5:0] y);
wire [5:0] oa=x+a,ob=x+b,oc=x+c;
always @* begin
 case(s[1:0])
  0:y=oa; 1:y=ob; 2:y=oc;
  default:case(s[3:2])
   0:y=a;1:y=b;2:y=c;
   default:case(s[5:4])
    0:y=a;1:y=b;2:y=c;default:y=(oa ^ a);
   endcase
  endcase
 endcase
end
endmodule
