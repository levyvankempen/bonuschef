# What bonuschef knows about you

Written for the people being invited, not for the person running it. If you
are about to hand somebody an invite code, hand them this too.

## What is stored

- **Your username and a password hash.** The hash is scrypt with a
  deliberately slow work factor. Somebody reading the database cannot get your
  password back out of it in any reasonable time.
- **Which Albert Heijn you shop at.** A store number and its name.
- **Which recipes you saved, which you said no to, and when you last made
  them.** Yours; nobody else's account can see them.
- **A session token hash**, so you stay signed in. Signing out revokes it.

## What is not stored

**Nothing about your Albert Heijn account.** No login, no password, no
bonuskaart, no orders, no address.

This is worth saying plainly because an earlier design did store it, and the
reasoning for dropping it is the reassuring part rather than a detail. The
plan was for each person to connect their own AH login, because clearance
prices were assumed to differ per customer. They do not: measured against four
real shops, the feed depends on the shop and not on who asks. So one Albert
Heijn session - the operator's - fetches every shop, and yours is never asked
for and never held.

## What other people can see

Other accounts see the shared recipe catalogue, which includes recipes you
add. They do not see which of them you saved, which you rejected, when you
last cooked something, your shop, or anything about your account.

The person running the server can read the database directly. That is true of
any system somebody else hosts, and is worth knowing rather than assuming
otherwise.

## Where it runs

On a small machine in the operator's home, reachable only over their private
network. It is not on the public internet. Nothing is sent anywhere else, and
there is no analytics or tracking of any kind.

## Ending it

Signing out revokes the session. Ask the operator to delete your account and
everything above goes with it - the schema removes your sessions and saved
recipes along with the account row, rather than leaving them behind.
