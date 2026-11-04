/* Used DFFEAS subset: prn=1, aload=asdata=sload=0; check pins before use.
 * Priority: asynchronous clear > enable > synchronous clear > synchronous load > data. */
module dffeas(output reg q,
             input d, clk, clrn, prn, ena, asdata, aload, sclr, sload);
  parameter power_up = "dontcare";
  parameter is_wysiwyg = "false";
  initial begin
    if (power_up == "low") q = 1'b0;
    else if (power_up == "high") q = 1'b1;
  end
  always @(posedge clk or negedge clrn) begin
    if (!clrn) q <= 1'b0;
    else if (ena) begin
      if (sclr) q <= 1'b0;
      else if (sload) q <= asdata;
      else q <= d;
    end
  end
endmodule
