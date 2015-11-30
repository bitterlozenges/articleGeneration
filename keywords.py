import rake.rake as rake


def genSeeds(text, numSeeds=10, maxWords=3, rake_obj=None):
	""" Returns a list of 'seeds', or keywords from text input.
		args:
			text     - text input (article)
			numSeeds - number of keywords you want to return
			maxWords - maximum phrase length. default means seeds will be
					   phrases of 3 words or less
		    rake_obj - optional RAKE object
	    returns:
	    	list of strings
	"""
	minChars = 5
	minFreq  = 3

	if not rake_obj:
		rake_obj = rake.Rake("rake/SmartStopList.txt", minChars, maxWords, minFreq)

	keywords = rake_obj.run(text)
	return [s for s, _ in keywords[:numSeeds]]


def genParSeeds(text, numSeeds=10, maxWords=3):
	""" Returns lists of 'seeds', one per paragraph.
		args:
			text     - text input (article)
			numSeeds - number of keywords you want to return
			maxWords - maximum phrase length. default means seeds will be
					   phrases of 3 words or less
	    returns:
	    	list of lists of strings
	"""
	minChars = 5
	minFreq  = 1

	paragraphs = text.split("\n")
	rake_obj = rake.Rake("rake/SmartStopList.txt", minChars, maxWords, minFreq)
	return [genSeeds(p, numSeeds, maxWords, rake_obj) for p in paragraphs]


# tests! CS50 Scrut
sample_file = open("article.txt", 'r')
txt = sample_file.read()
keywords = genSeeds(txt)
print "Keywords:", keywords
print "Paragraph Keywords:", genParSeeds(txt)
