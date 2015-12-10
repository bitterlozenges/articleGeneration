import random
import numpy

class CFG(object):
    def __init__(self, name, symbols_dict=None):
        self.name = name
        self.dict = symbols_dict
        # set of symbols we recognize
        self.symbolset = set()
        if symbols_dict:
            self.symbolset.update(symbols_dict.keys())
        # list of user-providable facts.
        self.user_provided = []

    def parse(self, str, append=False):
         """ Stores user-provided values for those specified in rules."""
        if not append:
            self.dict = {}
            self.symbolset = set()
        lines = str.split("\n")
        for line in lines:
            tokens = line.split(" ")

            if tokens == []:    # empty line
                continue
            symb = tokens[0]
            if symb == "" or symb[0] == "#":  # comment
                continue

            # user input required?
            if tokens[1] == "*":
                self.user_provided.append(symb)
                continue

            # update model
            if symb in self.dict:
                self.dict[symb].append(tokens[1:])
            else:
                self.dict[symb] = [tokens[1:]]
                self.symbolset.add(symb)

    def provide_variables(self):
        """ Stores user-provided values for those symbols specified in rules. """

        print "Provide comma separated values for each of the next symbols:"
        for symb in self.user_provided:
            s = raw_input(symb + "--> ")
            poss = s.split(",")
            poss = [p.split(" ") for p in poss]
            # user didn't provide input
            if not poss:
                continue
            self.dict[symb] = poss

    def expand(self, token, destroy=True):
        """
            Returns the fully expanded token into nonterminal symbols.

            args:
                token- the token to be expanded
                destroy - whether to destroy the probability array at the end of function
        """
        # clear probability dictionary at end
        if destroy:
            self.probs = {}

        # literal
        if self.literal(token):
            if token == "INT":
                return str(random.randrange(15))
            elif token == "\\n":
                return "\n"
            return token

        # add to probability dictionary if first time expanding
        if token not in self.probs:
            n = len(self.dict[token])
            self.probs[token] = [1.0/n]*n

        # choose an index
        i = numpy.random.choice(range(len(self.dict[token])), p=self.probs[token])
        expansion = self.dict[token][i]

        # decrease probability of this expansion
        self.probs[token][i] *= 0.8
        self.probs[token] = [float(p)/sum(self.probs[token]) for p in self.probs[token]]


        result = self.expand(expansion[0], False)
        for t in expansion[1:]:
            result += " "
            result += self.expand(t, False)
            # if self.literal(t):
            #     result += t # no preceding space for literal
            # else:
            #     result += " "
            #     result += self.expand(token)

        if destroy:
            self.probs = {}

        return result

    def generate(self):
        return self.expand(self.name)

    def literal(self, s):
        return s not in self.symbolset




# Start here!
if __name__ == '__main__':
    f = open("rules.txt")
    input_str = f.read()
    c = CFG('ARTICLE')
    c.parse(input_str)
    c.provide_variables()

    print c.generate()
