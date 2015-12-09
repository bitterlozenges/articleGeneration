# -*- coding: utf-8 -*-
from __future__ import division
import re
import sqlite3
from HTMLParser import HTMLParser
from functools import wraps
try:
    import cPickle as pickle
except ImportError:
    import pickle
import logging
import os
import random
from collections import defaultdict

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


class StringContinuationImpossibleError(Exception):
    pass



# {words: {word: prob}}
# We have to define these as separate functions so they can be pickled.
def _db_factory():
    return defaultdict(_one_dict)

def _one():
    return 1.0

def _one_dict():
    return defaultdict(_one)

def _wordIter(text, separator='.'):
    """
    An iterator over the 'words' in the given text, as defined by
    the regular expression given as separator.
    """
    exp = re.compile(separator)
    pos = 0
    for occ in exp.finditer(text):
        sub = text[pos:occ.start()].strip()
        if sub:
            yield sub
        pos = occ.start() + 1
    if pos < len(text):
        # take case of the last part
        sub = text[pos:].strip()
        if sub:
            yield sub

class MarkovChain(object):
    def __init__(self, dbFilePath=None):
        self.dbFilePath = dbFilePath
        if not dbFilePath:
            self.dbFilePath = os.path.join(os.path.dirname(__file__), "markovdb")
        try:
            with open(self.dbFilePath, 'rb') as dbfile:
                self.db = pickle.load(dbfile)
        except (IOError, ValueError):
            logging.warn('Database file corrupt or not found, using empty database')
            self.db = _db_factory()

    def generateDatabase(self, data, sentenceSep='[.!?\n]', n=2):
        """ Generate word probability database from raw content string """
        self.db[('',)][''] = 0.0
        z = 0
        print "asdfs"
        for row in data:
            z+=1
            if z%10 == 0:
                print z
            # I'm using the database to temporarily store word counts
            s = strip_tags(row[2])
            the_str = re.sub(ur'[^\w_ .,\’-]+', u' ', s, flags=re.UNICODE)
            textSample = _wordIter(the_str, sentenceSep)  # get an iterator for the 'sentences'
            # We're using '' as special symbol for the beginning
            # of a sentence
            for line in textSample:
                words = line.strip().split()  # split words in line
                if len(words) == 0:
                    continue
                # first word follows a sentence end
                self.db[("",)][words[0]] += 1

                for order in range(1, n+1):
                    for i in range(len(words) - 1):
                        if i + order >= len(words):
                            continue
                        word = tuple(words[i:i + order])
                        self.db[word][words[i + order]] += 1

                    # last word precedes a sentence end
                    self.db[tuple(words[len(words) - order:len(words)])][""] += 1

        # We've now got the db filled with parametrized word counts
        # We still need to normalize this to represent probabilities
        z=0
        for word in self.db:
            z+=1
            if z%10 == 0:
                print z
            wordsum = 0
            for nextword in self.db[word]:
                wordsum += self.db[word][nextword]
            if wordsum != 0:
                for nextword in self.db[word]:
                    self.db[word][nextword] /= wordsum

    def dumpdb(self):
        try:
            print "trying dump"
            with open(self.dbFilePath, 'wb') as dbfile:
                pickle.dump(self.db, dbfile)
            # It looks like db was written successfully
            return True
        except IOError:
            logging.warn('Database file could not be written')
            return False

    def generateString(self):
        """ Generate a "sentence" with the database of known text """
        return self._accumulateWithSeed(('',))

    def generateStringWithSeed(self, seed):
        """ Generate a "sentence" with the database and a given word """
        # using str.split here means we're contructing the list in memory
        # but as the generated sentence only depends on the last word of the seed
        # I'm assuming seeds tend to be rather short.
        words = seed.split()
        if (words[-1],) not in self.db:
            # The only possible way it won't work is if the last word is not known
            raise StringContinuationImpossibleError('Could not continue string: '
                                                    + seed)
        return self._accumulateWithSeed(words)

    def _accumulateWithSeed(self, seed):
        """ Accumulate the generated sentence with a given single word as a
        seed """
        nextWord = self._nextWord(seed)
        sentence = list(seed) if seed else []
        while nextWord:
            sentence.append(nextWord)
            nextWord = self._nextWord(sentence)
        return ' '.join(sentence).strip()

    def _nextWord(self, lastwords):
        lastwords = tuple(lastwords)
        if lastwords != ('',):
            while lastwords not in self.db:
                lastwords = lastwords[1:]
                if not lastwords:
                    return ''
        probmap = self.db[lastwords]
        sample = random.random()
        # since rounding errors might make us miss out on some words
        maxprob = 0.0
        maxprobword = ""
        for candidate in probmap:
            # remember which word had the highest probability
            # this is the word we'll default to if we can't find anythin else
            if probmap[candidate] > maxprob:
                maxprob = probmap[candidate]
                maxprobword = candidate
            if sample > probmap[candidate]:
                sample -= probmap[candidate]
            else:
                return candidate
        # getting here means we haven't found a matching word. :(
        return maxprobword


class MLStripper(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self)
        self.reset()
        self.fed = []

    def handle_data(self, d):
        self.fed.append(d)

    def handle_entityref(self, name):
        self.fed.append('&%s;' % name)

    def handle_charref(self, name):
        self.fed.append('&#%s;' % name)

    def get_data(self):
        return ''.join(self.fed)


def _strip_once(value):
    """
    Internal tag stripping utility used by strip_tags.
    """
    s = MLStripper()
    try:
        s.feed(value)
    except HTMLParseError:
        return value
    try:
        s.close()
    except HTMLParseError:
        return s.get_data() + s.rawdata
    else:
        return s.get_data()


def strip_tags(value):
    """Returns the given HTML with all tags stripped."""
    # Note: in typical case this loop executes _strip_once once. Loop condition
    # is redundant, but helps to reduce number of executions of _strip_once.
    while '<' in value and '>' in value:
        new_value = _strip_once(value)
        if len(new_value) >= len(value):
            # _strip_once was not able to detect more tags or length increased
            # due to http://bugs.python.org/issue20288
            # (affects Python 2 < 2.7.7 and Python 3 < 3.3.5)
            break
        value = new_value
    return value


# mc = MarkovChain("/Users/skaplan/Dropbox/Harvard2015/CS182/final/markov2")
# while 1 == 1:
#     foo=raw_input('Press enter to generate an article based on article.txt \n')
#     sample_file = open("article.txt", 'r')
#     txt = sample_file.read()
#     paragraphs = genParSeeds(txt)
    
#     for keywords in paragraphs:  
#       fin_str = ""
#       for keyword in keywords:
#       	try:
#       		a = mc.generateStringWithSeed(keyword)[(len(keyword)+1):]
#       		fin_str += (a.capitalize() + "| ")
#       	except Exception:
#             pass
#         try:
#             #print mc.generateStringWithSeed(foo)
#             fin_str += (mc.generateStringWithSeed(keyword) + ". ")
#         except Exception:
#             pass
#       print fin_str
#       if not (fin_str == ""):
#       	print "\n"

try:
    print "wut"
    con = sqlite3.connect('data.db')
    
    cur = con.cursor()    
    cur.execute('SELECT * FROM articles')
    the_str = ""
    data = cur.fetchall()
    i=0
    words = 0
    for row in data:
        s = strip_tags(row[2])
        words += len(s.split(" "))
        i += 1
    print "words " + str(words)
    print "i ", i
        
    #     i+=1
    #     if i == 10:
    #         break
    #mc = MarkovChain("/Users/skaplan/Dropbox/Harvard2015/CS182/final/markov2")
    #mc.generateDatabase(data)
    #mc.dumpdb()
    #print mc.generateString()

except sqlite3.Error, e:
    
    print "Error %s:" % e.args[0]
    sys.exit(1)
    
finally:
    
    if con:
        con.close()


    #re.sub(ur'[^\w_ .,\’]+', u'', s, flags=re.UNICODE)