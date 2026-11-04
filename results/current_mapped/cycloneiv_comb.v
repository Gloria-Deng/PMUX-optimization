module cycloneiv_lcell_comb
  (output combout, cout,
   input dataa, datab, datac, datad, cin);

   parameter lut_mask = 16'hFFFF;
   parameter sum_lutc_input = "datac";
   parameter dont_touch = "off";
   parameter lpm_type = "cycloneiv_lcell_comb";

   function lut_data;
      input [15:0] mask;
      input        a, b, c, d;
      reg [7:0]    s3;
      reg [3:0]    s2;
      reg [1:0]    s1;
      begin
         s3 = d ? mask[15:8] : mask[7:0];
         s2 = c ?   s3[7:4]  :   s3[3:0];
         s1 = b ?   s2[3:2]  :   s2[1:0];
         lut_data = a ? s1[1] : s1[0];
      end
   endfunction

   wire arithmetic = (sum_lutc_input == "cin");
   assign combout = lut_data(lut_mask, dataa, datab, arithmetic ? cin : datac, datad);
   assign cout    = lut_data(lut_mask, dataa, datab, cin, 1'b0);
endmodule

