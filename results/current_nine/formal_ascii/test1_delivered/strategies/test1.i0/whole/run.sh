yosys -ql run.log run.ys
if grep "SAT temporal induction proof finished - model found for base case: FAIL!" run.log > /dev/null ; then
	echo FAIL > status
	echo "Could not prove equivalence of partition 'test1.i0' using strategy 'whole': partitions not equivalent"
elif grep "Reached maximum number of time steps -> proof failed." run.log > /dev/null ; then
	echo UNKNOWN > status
	echo "Could not prove equivalence of partition 'test1.i0' using strategy 'whole': equivalence unknown"
elif grep "Interrupted SAT solver: TIMEOUT!" run.log > /dev/null ; then
	echo UNKNOWN > status
	echo "Could not prove equivalence of partition 'test1.i0' using strategy 'whole': timeout"
elif grep "Induction step proven: SUCCESS!" run.log > /dev/null ; then
	echo PASS > status
	echo "Proved equivalence of partition 'test1.i0' using strategy 'whole'"
else
	echo ERROR > status
	echo "Execution of strategy 'whole' on partition 'test1.i0' encountered an error.
Details can be found in 'test1_delivered/strategies/test1.i0/whole/run.log'."
	exit 1
fi
exit 0

