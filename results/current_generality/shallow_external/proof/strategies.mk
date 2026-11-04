.DEFAULT_GOAL := all

strategies/shallow_external.exposed/whole/status:
	@echo "Running strategy 'whole' on 'shallow_external.exposed'.."
	@bash -c "cd strategies/shallow_external.exposed/whole; source run.sh"

.PHONY: all summary
all: strategies/shallow_external.exposed/whole/status
	$(MAKE) -f strategies.mk summary
summary:
	@rc=0 ; \
	while read f; do \
		p=$${f#strategies/} ; p=$${p%/*/status} ; \
		if grep -q "PASS" $$f ; then \
			echo "* Successfully proved equivalence of partition $$p" ; \
		else \
			echo "* Failed to prove equivalence of partition $$p" ; rc=1 ; \
		fi ; \
	done < summary_targets.list ; \
	if [ "$$rc" -eq 0 ] ; then \
		echo "* Successfully proved designs equivalent" ; \
	fi
