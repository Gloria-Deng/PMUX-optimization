yosys -ql run.log run.ys
if grep "SAT temporal induction proof finished - model found for base case: FAIL!" run.log > /dev/null ; then
	echo FAIL > status
	echo "Could not prove equivalence of partition 'shallow_constants.y' using strategy 'whole': partitions not equivalent"
elif grep "Reached maximum number of time steps -> proof failed." run.log > /dev/null ; then
	echo UNKNOWN > status
	echo "Could not prove equivalence of partition 'shallow_constants.y' using strategy 'whole': equivalence unknown"
elif grep "Interrupted SAT solver: TIMEOUT!" run.log > /dev/null ; then
	echo UNKNOWN > status
	echo "Could not prove equivalence of partition 'shallow_constants.y' using strategy 'whole': timeout"
elif grep "Induction step proven: SUCCESS!" run.log > /dev/null ; then
	echo PASS > status
	echo "Proved equivalence of partition 'shallow_constants.y' using strategy 'whole'"
else
	echo ERROR > status
	echo "Execution of strategy 'whole' on partition 'shallow_constants.y' encountered an error.
Details can be found in 'proof/strategies/shallow_constants.y/whole/run.log'."
	exit 1
fi
exit 0

