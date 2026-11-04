attribute \top 1
module \audit
  wire width 8 input 1 \d0
  wire width 8 input 2 \d1
  wire width 8 input 3 \d2
  wire width 8 input 4 \d3
  wire width 3 input 5 \s
  wire width 8 output 6 \y
  wire width 8 $n1
  wire width 8 $n2
  cell $mux \m1
    parameter \WIDTH 8
    connect \A \d0
    connect \B \d1
    connect \S \s [0]
    connect \Y $n1
  end
  cell $mux \m2
    parameter \WIDTH 8
    connect \A { $n1 [0] $n1 [1] $n1 [2] $n1 [3] $n1 [4] $n1 [5] $n1 [6] $n1 [7] }
    connect \B \d2
    connect \S \s [1]
    connect \Y $n2
  end
  cell $mux \m3
    parameter \WIDTH 8
    connect \A $n2
    connect \B \d3
    connect \S \s [2]
    connect \Y \y
  end
end
