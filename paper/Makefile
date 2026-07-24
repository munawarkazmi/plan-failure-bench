.PHONY: all tectonic clean

all:
	latexmk -pdf -interaction=nonstopmode paper.tex

tectonic:
	tectonic paper.tex

clean:
	latexmk -C 2>/dev/null || true
	rm -f paper.bbl paper.run.xml
