#!/usr/bin/python
"""This simple script converts all occurences of the pattern
<p>[n] (where n is an integer) into a HTML anchor of the name "[n]" """

import re

s = re.compile(r"<p>\[[\d]+\]")
n = re.compile(r"\[[\d]+\]")

def makeref(str):
	try:
		match = s.search(str).group()
		num = int(n.search(match).group()[1:-1])
		return s.sub(r'<p><a name = "[%d]">[%d]</a>' % (num, num), str)
	except:
		return str
	
if __name__ == "__main__":
	import sys
	
	try:
		f = open(sys.argv[1])
	except:
		print "usage: makeref <filename>"
		exit(1)
		
	for line in f.readlines():
		print makeref(line)