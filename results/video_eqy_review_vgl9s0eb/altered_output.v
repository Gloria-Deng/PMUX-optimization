module pmux_case05_nested(input wire clk, rst, en, input wire [47:0] data_in, input wire [15:0] ctrl_in, output wire [11:0] data_out);
wire [11:0] actual;
nested_original u (.clk(clk), .rst(rst), .en(en), .data_in(data_in), .ctrl_in(ctrl_in), .data_out(actual));
assign data_out = actual ^ 12'h001;
endmodule
